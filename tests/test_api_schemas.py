"""Tests for API schemas and category mapping."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from crimecity3k.api.categories import (
    CATEGORY_TYPES,
    TYPE_TO_CATEGORY,
    get_all_categories,
    get_category,
)
from crimecity3k.api.main import app
from crimecity3k.api.schemas import (
    EventResponse,
    EventsListResponse,
    TypeHierarchy,
    TypeInfo,
)


class TestCategoryMapping:
    """Tests for category→type mapping."""

    def test_all_expected_categories_defined(self) -> None:
        """All 8 categories should be defined (including 'other')."""
        expected = {
            "traffic",
            "property",
            "violence",
            "narcotics",
            "fraud",
            "public_order",
            "weapons",
            "other",
        }
        assert set(CATEGORY_TYPES.keys()) == expected

    def test_traffic_category_types(self) -> None:
        """Traffic category should have correct types."""
        assert "Trafikolycka, personskada" in CATEGORY_TYPES["traffic"]
        assert "Rattfylleri" in CATEGORY_TYPES["traffic"]
        assert "Trafikolycka" in CATEGORY_TYPES["traffic"]  # Generic variant
        assert "Trafikkontroll" in CATEGORY_TYPES["traffic"]
        assert len(CATEGORY_TYPES["traffic"]) >= 10  # At least 10 traffic types

    def test_property_category_types(self) -> None:
        """Property category should have correct types."""
        assert "Stöld" in CATEGORY_TYPES["property"]
        assert "Rån väpnat" in CATEGORY_TYPES["property"]
        assert "Motorfordon, stöld" in CATEGORY_TYPES["property"]
        assert len(CATEGORY_TYPES["property"]) >= 10  # At least 10 property types

    def test_violence_category_types(self) -> None:
        """Violence category should have correct types."""
        assert "Misshandel" in CATEGORY_TYPES["violence"]
        assert "Mord/dråp" in CATEGORY_TYPES["violence"]
        assert "Olaga hot" in CATEGORY_TYPES["violence"]  # Now included
        assert len(CATEGORY_TYPES["violence"]) >= 10  # At least 10 violence types

    def test_type_to_category_reverse_lookup(self) -> None:
        """TYPE_TO_CATEGORY should correctly reverse the mapping."""
        assert TYPE_TO_CATEGORY["Stöld"] == "property"
        assert TYPE_TO_CATEGORY["Misshandel"] == "violence"
        assert TYPE_TO_CATEGORY["Narkotikabrott"] == "narcotics"

    def test_get_category_known_type(self) -> None:
        """get_category should return correct category for known types."""
        assert get_category("Stöld") == "property"
        assert get_category("Trafikolycka, personskada") == "traffic"

    def test_get_category_unknown_type_returns_other(self) -> None:
        """get_category should return 'other' for unknown types."""
        assert get_category("Okänd händelse") == "other"
        assert get_category("") == "other"

    def test_get_all_categories_includes_other(self) -> None:
        """get_all_categories should include all 8 categories including 'other'."""
        categories = get_all_categories()
        assert "other" in categories
        assert "traffic" in categories
        assert "violence" in categories
        assert len(categories) == 8


class TestEventResponseSchema:
    """Tests for EventResponse Pydantic model."""

    def test_event_response_all_fields(self) -> None:
        """EventResponse should accept all required fields."""
        event = EventResponse(
            event_id="123",
            event_datetime=datetime(2024, 1, 15, 10, 30),
            type="Stöld",
            category="property",
            location_name="Stockholm",
            summary="A theft occurred",
            html_body="Detailed description",
            police_url="https://polisen.se/event/123",
            latitude=59.329,
            longitude=18.068,
        )
        assert event.event_id == "123"
        assert event.type == "Stöld"

    def test_event_response_html_body_optional(self) -> None:
        """EventResponse should allow null html_body."""
        event = EventResponse(
            event_id="123",
            event_datetime=datetime(2024, 1, 15, 10, 30),
            type="Stöld",
            category="property",
            location_name="Stockholm",
            summary="A theft occurred",
            html_body=None,  # Optional field
            police_url="https://polisen.se/event/123",
            latitude=59.329,
            longitude=18.068,
        )
        assert event.html_body is None


class TestEventsListResponseSchema:
    """Tests for EventsListResponse Pydantic model."""

    def test_events_list_response_structure(self) -> None:
        """EventsListResponse should have correct structure."""
        event = EventResponse(
            event_id="1",
            event_datetime=datetime.now(),
            type="Stöld",
            category="property",
            location_name="Stockholm",
            summary="Test",
            police_url="https://polisen.se/",
            latitude=59.0,
            longitude=18.0,
        )
        response = EventsListResponse(
            total=100,
            page=1,
            per_page=50,
            events=[event],
        )
        assert response.total == 100
        assert response.page == 1
        assert len(response.events) == 1


class TestTypeHierarchySchema:
    """Tests for TypeHierarchy Pydantic model."""

    def test_type_hierarchy_structure(self) -> None:
        """TypeHierarchy should accept dict of category→types with translations."""
        hierarchy = TypeHierarchy(
            categories={
                "traffic": [TypeInfo(se="Trafikolycka", en="Traffic Accident")],
                "property": [
                    TypeInfo(se="Stöld", en="Theft"),
                    TypeInfo(se="Inbrott", en="Burglary"),
                ],
            }
        )
        assert "traffic" in hierarchy.categories
        assert len(hierarchy.categories["property"]) == 2
        assert hierarchy.categories["traffic"][0].en == "Traffic Accident"


class TestAPIStubEndpoints:
    """Tests for API endpoints without database (testing graceful degradation)."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client for API."""
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_types_endpoint(self, client: TestClient) -> None:
        """Types endpoint should return category hierarchy."""
        response = client.get("/api/types")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "traffic" in data["categories"]
        assert "property" in data["categories"]

    def test_events_endpoint_requires_database(self, client: TestClient) -> None:
        """Events endpoint returns 503 when database is not initialized."""
        response = client.get("/api/events?h3_cell=85283473fffffff")
        # Without database initialization via lifespan, returns 503
        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == "Database not initialized"

    def test_events_endpoint_requires_location_param(self, client: TestClient) -> None:
        """Events endpoint requires either h3_cell or location_name parameter."""
        response = client.get("/api/events")
        assert response.status_code == 400  # Must specify h3_cell or location_name
        assert "h3_cell" in response.json()["detail"]
        assert "location_name" in response.json()["detail"]

    def test_events_endpoint_per_page_max_100(self, client: TestClient) -> None:
        """Events endpoint should cap per_page at 100."""
        response = client.get("/api/events?h3_cell=test&per_page=200")
        assert response.status_code == 422  # Validation error

    def test_openapi_docs_available(self, client: TestClient) -> None:
        """OpenAPI docs should be available at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200
