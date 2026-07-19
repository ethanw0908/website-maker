from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class PlaceResult:
    place_id: str
    name: str
    category: str | None
    address: str | None
    phone: str | None
    website_url: str | None
    rating: float | None
    review_count: int
    business_status: str | None
    google_maps_url: str | None


class GooglePlacesClient:
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    field_mask = ",".join([
        "places.id", "places.displayName", "places.primaryType", "places.formattedAddress",
        "places.nationalPhoneNumber", "places.websiteUri", "places.rating",
        "places.userRatingCount", "places.businessStatus", "places.googleMapsUri",
    ])

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, max_results: int = 20) -> list[PlaceResult]:
        if not self.settings.google_places_api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY is not configured")
        headers = {
            "X-Goog-Api-Key": self.settings.google_places_api_key,
            "X-Goog-FieldMask": self.field_mask,
        }
        payload = {"textQuery": query, "pageSize": min(max_results, 20)}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        results: list[PlaceResult] = []
        for place in data.get("places", []):
            results.append(PlaceResult(
                place_id=place["id"],
                name=place.get("displayName", {}).get("text", "Unknown business"),
                category=place.get("primaryType"),
                address=place.get("formattedAddress"),
                phone=place.get("nationalPhoneNumber"),
                website_url=place.get("websiteUri"),
                rating=place.get("rating"),
                review_count=place.get("userRatingCount", 0),
                business_status=place.get("businessStatus"),
                google_maps_url=place.get("googleMapsUri"),
            ))
        return results
