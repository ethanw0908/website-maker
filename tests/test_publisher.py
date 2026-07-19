from app.services.publisher import slugify


def test_slugify_repository_name():
    assert slugify("North Shore Heating & Air") == "north-shore-heating-air"
