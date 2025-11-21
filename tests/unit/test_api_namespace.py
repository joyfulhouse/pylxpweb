"""Unit tests for API Namespace.

This module tests the APINamespace class and the client.api property,
ensuring the new v0.2.0 API organization works correctly.
"""

from __future__ import annotations

from pylxpweb import LuxpowerClient
from pylxpweb.api_namespace import APINamespace
from pylxpweb.endpoints import (
    AnalyticsEndpoints,
    ControlEndpoints,
    DeviceEndpoints,
    ExportEndpoints,
    FirmwareEndpoints,
    ForecastingEndpoints,
    PlantEndpoints,
)


class TestAPINamespaceProperty:
    """Test the client.api property."""

    def test_api_namespace_exists(self) -> None:
        """Test that client.api property exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client, "api"), "Client should have 'api' property"

    def test_api_namespace_returns_instance(self) -> None:
        """Test that client.api returns APINamespace instance."""
        client = LuxpowerClient("test_user", "test_pass")
        api = client.api
        assert isinstance(api, APINamespace), "client.api should return APINamespace instance"

    def test_api_namespace_singleton(self) -> None:
        """Test that client.api returns same instance on multiple calls."""
        client = LuxpowerClient("test_user", "test_pass")
        api1 = client.api
        api2 = client.api
        assert api1 is api2, "client.api should return same instance (singleton pattern)"

    def test_api_namespace_has_client_reference(self) -> None:
        """Test that APINamespace has reference to client."""
        client = LuxpowerClient("test_user", "test_pass")
        api = client.api
        assert api._client is client, "APINamespace should have reference to client"


class TestAPINamespaceEndpointProperties:
    """Test that all endpoint groups are accessible via api namespace."""

    def test_api_has_plants_property(self) -> None:
        """Test that client.api.plants exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "plants"), "api namespace should have 'plants' property"

    def test_api_has_devices_property(self) -> None:
        """Test that client.api.devices exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "devices"), "api namespace should have 'devices' property"

    def test_api_has_control_property(self) -> None:
        """Test that client.api.control exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "control"), "api namespace should have 'control' property"

    def test_api_has_analytics_property(self) -> None:
        """Test that client.api.analytics exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "analytics"), "api namespace should have 'analytics' property"

    def test_api_has_forecasting_property(self) -> None:
        """Test that client.api.forecasting exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "forecasting"), (
            "api namespace should have 'forecasting' property"
        )

    def test_api_has_export_property(self) -> None:
        """Test that client.api.export exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "export"), "api namespace should have 'export' property"

    def test_api_has_firmware_property(self) -> None:
        """Test that client.api.firmware exists."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client.api, "firmware"), "api namespace should have 'firmware' property"


class TestAPINamespaceEndpointInstances:
    """Test that endpoint properties return correct instances."""

    def test_plants_returns_plant_endpoints(self) -> None:
        """Test that client.api.plants returns PlantEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        plants = client.api.plants
        assert isinstance(plants, PlantEndpoints), (
            "client.api.plants should return PlantEndpoints instance"
        )

    def test_devices_returns_device_endpoints(self) -> None:
        """Test that client.api.devices returns DeviceEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        devices = client.api.devices
        assert isinstance(devices, DeviceEndpoints), (
            "client.api.devices should return DeviceEndpoints instance"
        )

    def test_control_returns_control_endpoints(self) -> None:
        """Test that client.api.control returns ControlEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        control = client.api.control
        assert isinstance(control, ControlEndpoints), (
            "client.api.control should return ControlEndpoints instance"
        )

    def test_analytics_returns_analytics_endpoints(self) -> None:
        """Test that client.api.analytics returns AnalyticsEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        analytics = client.api.analytics
        assert isinstance(analytics, AnalyticsEndpoints), (
            "client.api.analytics should return AnalyticsEndpoints instance"
        )

    def test_forecasting_returns_forecasting_endpoints(self) -> None:
        """Test that client.api.forecasting returns ForecastingEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        forecasting = client.api.forecasting
        assert isinstance(forecasting, ForecastingEndpoints), (
            "client.api.forecasting should return ForecastingEndpoints instance"
        )

    def test_export_returns_export_endpoints(self) -> None:
        """Test that client.api.export returns ExportEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        export = client.api.export
        assert isinstance(export, ExportEndpoints), (
            "client.api.export should return ExportEndpoints instance"
        )

    def test_firmware_returns_firmware_endpoints(self) -> None:
        """Test that client.api.firmware returns FirmwareEndpoints instance."""
        client = LuxpowerClient("test_user", "test_pass")
        firmware = client.api.firmware
        assert isinstance(firmware, FirmwareEndpoints), (
            "client.api.firmware should return FirmwareEndpoints instance"
        )


class TestAPINamespaceLazyLoading:
    """Test that endpoint instances are lazy-loaded (singleton per namespace)."""

    def test_plants_lazy_loaded_singleton(self) -> None:
        """Test that plants endpoint is lazy-loaded and returns same instance."""
        client = LuxpowerClient("test_user", "test_pass")
        api = client.api

        # First access should create instance
        plants1 = api.plants
        assert plants1 is not None

        # Second access should return same instance
        plants2 = api.plants
        assert plants1 is plants2, "api.plants should return same instance (lazy-load singleton)"

    def test_devices_lazy_loaded_singleton(self) -> None:
        """Test that devices endpoint is lazy-loaded and returns same instance."""
        client = LuxpowerClient("test_user", "test_pass")
        api = client.api

        devices1 = api.devices
        devices2 = api.devices
        assert devices1 is devices2, "api.devices should return same instance (lazy-load singleton)"

    def test_control_lazy_loaded_singleton(self) -> None:
        """Test that control endpoint is lazy-loaded and returns same instance."""
        client = LuxpowerClient("test_user", "test_pass")
        api = client.api

        control1 = api.control
        control2 = api.control
        assert control1 is control2, "api.control should return same instance (lazy-load singleton)"


class TestEndpointClientReference:
    """Test that all endpoint instances have correct client reference."""

    def test_plants_has_client_reference(self) -> None:
        """Test that PlantEndpoints has reference to client."""
        client = LuxpowerClient("test_user", "test_pass")
        plants = client.api.plants
        assert plants.client is client, "PlantEndpoints should have reference to client"

    def test_devices_has_client_reference(self) -> None:
        """Test that DeviceEndpoints has reference to client."""
        client = LuxpowerClient("test_user", "test_pass")
        devices = client.api.devices
        assert devices.client is client, "DeviceEndpoints should have reference to client"

    def test_control_has_client_reference(self) -> None:
        """Test that ControlEndpoints has reference to client."""
        client = LuxpowerClient("test_user", "test_pass")
        control = client.api.control
        assert control.client is client, "ControlEndpoints should have reference to client"


class TestOldStylePropertiesStillWork:
    """Test old-style direct properties (backward compatibility during transition)."""

    def test_old_style_plants_property_exists(self) -> None:
        """Test that client.plants still exists for backward compatibility."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client, "plants"), "client.plants should still exist for compatibility"

    def test_old_style_devices_property_exists(self) -> None:
        """Test that client.devices still exists for backward compatibility."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client, "devices"), "client.devices should still exist for compatibility"

    def test_old_style_control_property_exists(self) -> None:
        """Test that client.control still exists for backward compatibility."""
        client = LuxpowerClient("test_user", "test_pass")
        assert hasattr(client, "control"), "client.control should still exist for compatibility"

    def test_old_style_returns_same_type_as_new(self) -> None:
        """Test that old-style properties return same type as new API namespace."""
        client = LuxpowerClient("test_user", "test_pass")

        # Both should return PlantEndpoints instances
        old_plants = client.plants
        new_plants = client.api.plants

        assert isinstance(old_plants, PlantEndpoints)
        assert isinstance(new_plants, PlantEndpoints)


class TestAPINamespaceDocstrings:
    """Test that API namespace has proper documentation."""

    def test_api_namespace_has_docstring(self) -> None:
        """Test that APINamespace class has docstring."""
        assert APINamespace.__doc__ is not None, "APINamespace should have class docstring"

    def test_api_property_has_docstring(self) -> None:
        """Test that client.api property has docstring."""
        assert LuxpowerClient.api.__doc__ is not None, "client.api property should have docstring"

    def test_plants_property_has_docstring(self) -> None:
        """Test that api.plants property has docstring."""
        assert APINamespace.plants.__doc__ is not None, "api.plants property should have docstring"

    def test_devices_property_has_docstring(self) -> None:
        """Test that api.devices property has docstring."""
        assert APINamespace.devices.__doc__ is not None, (
            "api.devices property should have docstring"
        )

    def test_control_property_has_docstring(self) -> None:
        """Test that api.control property has docstring."""
        assert APINamespace.control.__doc__ is not None, (
            "api.control property should have docstring"
        )
