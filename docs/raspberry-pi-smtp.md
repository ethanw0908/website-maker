# Raspberry Pi outbound SMTP for LocalSite Agent

This configures an **outbound-only Postfix server** on the Debian host. LocalSite Agent connects to it from Docker. It does not create an inbox or IMAP service.

## Before installing

Direct delivery is practical only when you have:

- A domain you control
- A stable public IPv4 address
- Outbound TCP port 25 available from your internet connection
- A PTR/reverse-DNS record that your ISP or hosting provider can set to `mail.yourdomain.example`

Without those, use Postfix as a local relay through a reputable upstream SMTP service. Messages sent directly without aligned SPF, DKIM, DMARC, forward DNS, and reverse DNS are likely to be rejected or classified as spam.

Test outbound port 25:

```bash
nc -vz gmail-smtp-in.l.google.com 25
```

## Install Postfix and OpenDKIM

Replace the example values before running the commands:

```bash
export MAIL_DOMAIN="yourdomain.example"
export MAIL_HOSTNAME="mail.yourdomain.example"

sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  postfix opendkim opendkim-tools mailutils dnsutils swaks
```

Configure Postfix as an outbound relay for localhost and Docker networks only:

```bash
sudo postconf -e "myhostname = ${MAIL_HOSTNAME}"
sudo postconf -e "mydomain = ${MAIL_DOMAIN}"
sudo postconf -e "myorigin = ${MAIL_DOMAIN}"
sudo postconf -e "inet_interfaces = all"
sudo postconf -e "inet_protocols = all"
sudo postconf -e "mydestination = localhost"
sudo postconf -e "mynetworks = 127.0.0.0/8 [::1]/128 172.16.0.0/12"
sudo postconf -e "smtpd_relay_restrictions = permit_mynetworks,reject_unauth_destination"
sudo postconf -e "smtp_tls_security_level = may"
sudo postconf -e "smtpd_tls_security_level = may"
```

Do not forward public router port 25 to the Pi for this outbound-only configuration.

## Create a DKIM key

```bash
sudo mkdir -p "/etc/opendkim/keys/${MAIL_DOMAIN}"
sudo opendkim-genkey -b 2048 -d "${MAIL_DOMAIN}" \
  -D "/etc/opendkim/keys/${MAIL_DOMAIN}" -s mail
sudo chown -R opendkim:opendkim "/etc/opendkim/keys/${MAIL_DOMAIN}"
sudo chmod 700 "/etc/opendkim/keys/${MAIL_DOMAIN}"
sudo chmod 600 "/etc/opendkim/keys/${MAIL_DOMAIN}/mail.private"
```

Create `/etc/opendkim/TrustedHosts`:

```text
127.0.0.1
localhost
172.16.0.0/12
```

Create `/etc/opendkim/KeyTable`:

```text
mail._domainkey.yourdomain.example yourdomain.example:mail:/etc/opendkim/keys/yourdomain.example/mail.private
```

Create `/etc/opendkim/SigningTable`:

```text
*@yourdomain.example mail._domainkey.yourdomain.example
```

Add or replace these settings in `/etc/opendkim.conf`:

```text
Syslog                  yes
UMask                   002
Mode                    sv
Socket                  inet:8891@127.0.0.1
Canonicalization        relaxed/simple
OversignHeaders         From
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
```

Connect Postfix to OpenDKIM:

```bash
sudo postconf -e "milter_default_action = accept"
sudo postconf -e "milter_protocol = 6"
sudo postconf -e "smtpd_milters = inet:127.0.0.1:8891"
sudo postconf -e "non_smtpd_milters = inet:127.0.0.1:8891"

sudo systemctl enable --now opendkim postfix
sudo systemctl restart opendkim postfix
sudo postfix check
```

## DNS records

Publish these records with your DNS provider:

```text
mail.yourdomain.example.      A      YOUR_PUBLIC_IP
@                             TXT    "v=spf1 ip4:YOUR_PUBLIC_IP -all"
_dmarc                        TXT    "v=DMARC1; p=none; adkim=s; aspf=s; rua=mailto:dmarc@yourdomain.example"
```

Copy the DKIM TXT value from:

```bash
sudo cat "/etc/opendkim/keys/${MAIL_DOMAIN}/mail.txt"
```

Ask your ISP or VPS provider to set the public IP PTR record to exactly:

```text
mail.yourdomain.example
```

Forward DNS must resolve that hostname back to the same public IP.

## Connect LocalSite Agent

The Compose configuration maps `host.docker.internal` to the Debian host. In **Settings → SMTP connection**, use:

```text
SMTP host: host.docker.internal
Port: 25
Username: blank
Password: blank
STARTTLS: off
SSL/TLS: off
Enabled: on
From email: outreach@yourdomain.example
```

The Docker-to-host connection is local. Postfix uses opportunistic TLS when delivering to remote mail servers.

## Test and inspect

```bash
sudo journalctl -u postfix -u opendkim -f
```

From the Pi:

```bash
swaks --server 127.0.0.1 --from outreach@yourdomain.example --to YOUR_TEST_ADDRESS
```

Check the received message headers for `spf=pass`, `dkim=pass`, and `dmarc=pass` before sending any real outreach.
