"""Pydantic schemas for API request/response models.

Defines the contract for the events API endpoints, enabling
automatic OpenAPI documentation and request/response validation.
"""

from datetime import datetime as dt

from pydantic import BaseModel, Field


class EventResponse(BaseModel):
    """Single event in API response."""

    event_id: str = Field(description="Unique event identifier")
    event_datetime: dt = Field(description="Event timestamp")
    type: str = Field(description="Event type (Swedish, e.g., 'Stöld', 'Misshandel')")
    category: str = Field(description="Event category (traffic, property, violence, etc.)")
    location_name: str = Field(description="Location name (city/district)")
    summary: str = Field(description="Brief event summary")
    html_body: str | None = Field(
        default=None,
        description="Detailed event description (may be null if not available)",
    )
    police_url: str = Field(description="Full URL to police report on polisen.se")
    latitude: float = Field(description="Event latitude (WGS84)")
    longitude: float = Field(description="Event longitude (WGS84)")


class EventsListResponse(BaseModel):
    """Paginated list of events."""

    total: int = Field(description="Total number of matching events")
    page: int = Field(description="Current page number (1-indexed)")
    per_page: int = Field(description="Events per page")
    events: list[EventResponse] = Field(description="Events on current page")


class TypeHierarchy(BaseModel):
    """Category to event types mapping."""

    categories: dict[str, list[str]] = Field(
        description="Map of category name to list of event types"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    events_count: int = Field(description="Total events in database")
