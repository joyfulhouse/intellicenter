"""Tests for PoolModel and PoolObject classes."""

from typing import Any

from custom_components.intellicenter.pyintellicenter.attributes import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    FEATR_ATTR,
    OBJTYP_ATTR,
    PUMP_TYPE,
    SNAME_ATTR,
    STATUS_ATTR,
    SUBTYP_ATTR,
)
from custom_components.intellicenter.pyintellicenter.model import PoolModel, PoolObject


class TestPoolObject:
    """Tests for PoolObject class."""

    def test_create_pool_object(self):
        """Test creating a PoolObject."""
        obj = PoolObject(
            "TEST01",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "INTELLI",
                SNAME_ATTR: "Test Light",
                STATUS_ATTR: "OFF",
                "USE": "WHITER",
            },
        )

        assert obj.objnam == "TEST01"
        assert obj.objtype == CIRCUIT_TYPE
        assert obj.subtype == "INTELLI"
        assert obj.sname == "Test Light"
        assert obj.status == "OFF"
        assert obj["USE"] == "WHITER"

    def test_pool_object_is_a_light(self, pool_object_light: PoolObject):
        """Test isALight property for light subtypes."""
        assert pool_object_light.isALight is True
        assert pool_object_light.supportColorEffects is True

    def test_pool_object_not_a_light(self, pool_object_switch: PoolObject):
        """Test isALight property for non-light objects."""
        assert pool_object_switch.isALight is False
        assert pool_object_switch.supportColorEffects is False

    def test_pool_object_light_show(self):
        """Test isALightShow property."""
        show = PoolObject(
            "SHOW1",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "LITSHO",
                SNAME_ATTR: "Party Show",
                STATUS_ATTR: "OFF",
            },
        )
        assert show.isALightShow is True

    def test_pool_object_is_featured(self, pool_object_switch: PoolObject):
        """Test isFeatured property."""
        assert pool_object_switch.isFeatured is True

    def test_pool_object_not_featured(self):
        """Test isFeatured property for non-featured circuit."""
        obj = PoolObject(
            "CIRC02",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "GENERIC",
                SNAME_ATTR: "Aux Circuit",
                STATUS_ATTR: "OFF",
                FEATR_ATTR: "OFF",
            },
        )
        assert obj.isFeatured is False

    def test_pool_object_on_off_status_circuit(self, pool_object_light: PoolObject):
        """Test onStatus and offStatus for circuit objects."""
        assert pool_object_light.onStatus == "ON"
        assert pool_object_light.offStatus == "OFF"

    def test_pool_object_on_off_status_pump(self, pool_object_pump: PoolObject):
        """Test onStatus and offStatus for pump objects."""
        assert pool_object_pump.onStatus == "10"
        assert pool_object_pump.offStatus == "4"

    def test_pool_object_update_existing_attribute(self, pool_object_light: PoolObject):
        """Test updating an existing attribute."""
        changed = pool_object_light.update({STATUS_ATTR: "ON"})

        assert pool_object_light.status == "ON"
        assert STATUS_ATTR in changed
        assert changed[STATUS_ATTR] == "ON"

    def test_pool_object_update_new_attribute(self, pool_object_light: PoolObject):
        """Test adding a new attribute via update."""
        changed = pool_object_light.update({"NEW_ATTR": "value"})

        assert pool_object_light["NEW_ATTR"] == "value"
        assert "NEW_ATTR" in changed

    def test_pool_object_update_unchanged_value(self, pool_object_light: PoolObject):
        """Test updating with the same value returns no changes."""
        original_status = pool_object_light.status
        changed = pool_object_light.update({STATUS_ATTR: original_status})

        assert changed == {}

    def test_pool_object_update_multiple_attributes(
        self, pool_object_light: PoolObject
    ):
        """Test updating multiple attributes at once."""
        changed = pool_object_light.update(
            {
                STATUS_ATTR: "ON",
                "USE": "PARTY",
                "NEW_FIELD": "test",
            }
        )

        assert len(changed) == 3
        assert pool_object_light.status == "ON"
        assert pool_object_light["USE"] == "PARTY"
        assert pool_object_light["NEW_FIELD"] == "test"

    def test_pool_object_attributes_property(self, pool_object_light: PoolObject):
        """Test attributes property returns list of attribute keys."""
        attrs = pool_object_light.attributes
        assert isinstance(attrs, list)
        assert SNAME_ATTR in attrs
        assert STATUS_ATTR in attrs

    def test_pool_object_properties_property(self, pool_object_light: PoolObject):
        """Test properties property returns dict."""
        props = pool_object_light.properties
        assert isinstance(props, dict)
        assert SNAME_ATTR in props
        assert props[SNAME_ATTR] == "Pool Light"

    def test_pool_object_str_representation(self, pool_object_light: PoolObject):
        """Test string representation includes key info."""
        str_repr = str(pool_object_light)
        assert "LIGHT1" in str_repr
        assert CIRCUIT_TYPE in str_repr
        assert "INTELLI" in str_repr


class TestPoolModel:
    """Tests for PoolModel class."""

    def test_create_empty_pool_model(self):
        """Test creating an empty PoolModel."""
        model = PoolModel()
        assert model.numObjects == 0
        assert len(list(model.objectList)) == 0

    def test_pool_model_add_object(self):
        """Test adding a single object to the model."""
        model = PoolModel()
        obj = model.addObject(
            "LIGHT1",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "INTELLI",
                SNAME_ATTR: "Pool Light",
                STATUS_ATTR: "OFF",
            },
        )

        assert obj is not None
        assert model.numObjects == 1
        assert model["LIGHT1"] == obj

    def test_pool_model_add_objects_batch(self, pool_model_data: list[dict[str, Any]]):
        """Test adding multiple objects at once."""
        model = PoolModel()
        model.addObjects(pool_model_data)

        assert model.numObjects == len(pool_model_data)

    def test_pool_model_getitem(self, pool_model: PoolModel):
        """Test accessing objects by objnam using bracket notation."""
        light = pool_model["LIGHT1"]
        assert light is not None
        assert light.objnam == "LIGHT1"
        assert light.objtype == CIRCUIT_TYPE

    def test_pool_model_get_by_type(self, pool_model: PoolModel):
        """Test filtering objects by type."""
        bodies = pool_model.getByType(BODY_TYPE)
        assert len(bodies) == 2
        assert all(obj.objtype == BODY_TYPE for obj in bodies)

    def test_pool_model_get_by_type_and_subtype(self, pool_model: PoolModel):
        """Test filtering objects by type and subtype."""
        spa = pool_model.getByType(BODY_TYPE, "SPA")
        assert len(spa) == 1
        assert spa[0].objnam == "SPA01"
        assert spa[0].subtype == "SPA"

    def test_pool_model_get_children(self, pool_model: PoolModel):
        """Test getting children of an object."""
        # Add a parent-child relationship
        pool_model.addObject(
            "CHILD1",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "GENERIC",
                "PARENT": "POOL1",
                SNAME_ATTR: "Child Circuit",
            },
        )

        pool_body = pool_model["POOL1"]
        children = pool_model.getChildren(pool_body)

        assert len(children) >= 1
        assert any(c.objnam == "CHILD1" for c in children)

    def test_pool_model_iteration(self, pool_model: PoolModel):
        """Test iterating over all objects in the model."""
        count = 0
        for obj in pool_model:
            assert isinstance(obj, PoolObject)
            count += 1

        assert count == pool_model.numObjects

    def test_pool_model_object_list(self, pool_model: PoolModel):
        """Test objectList property."""
        objects = list(pool_model.objectList)
        assert len(objects) == pool_model.numObjects
        assert all(isinstance(obj, PoolObject) for obj in objects)

    def test_pool_model_objects_dict(self, pool_model: PoolModel):
        """Test objects property returns dict."""
        objects_dict = pool_model.objects
        assert isinstance(objects_dict, dict)
        assert "LIGHT1" in objects_dict
        assert objects_dict["LIGHT1"].objtype == CIRCUIT_TYPE

    def test_pool_model_process_updates(self, pool_model: PoolModel):
        """Test processing updates to multiple objects."""
        updates = [
            {
                "objnam": "LIGHT1",
                "params": {STATUS_ATTR: "ON"},
            },
            {
                "objnam": "PUMP1",
                "params": {STATUS_ATTR: "10", "RPM": "2500"},
            },
        ]

        changed = pool_model.processUpdates(updates)

        assert "LIGHT1" in changed
        assert changed["LIGHT1"][STATUS_ATTR] == "ON"
        assert "PUMP1" in changed
        assert changed["PUMP1"]["RPM"] == "2500"

        assert pool_model["LIGHT1"].status == "ON"
        assert pool_model["PUMP1"]["RPM"] == "2500"

    def test_pool_model_process_updates_unchanged(self, pool_model: PoolModel):
        """Test processing updates with no actual changes."""
        original_status = pool_model["LIGHT1"].status
        updates = [
            {
                "objnam": "LIGHT1",
                "params": {STATUS_ATTR: original_status},
            },
        ]

        changed = pool_model.processUpdates(updates)

        assert changed == {}

    def test_pool_model_process_updates_unknown_object(self, pool_model: PoolModel):
        """Test processing updates for non-existent object."""
        updates = [
            {
                "objnam": "UNKNOWN",
                "params": {STATUS_ATTR: "ON"},
            },
        ]

        changed = pool_model.processUpdates(updates)

        assert changed == {}

    def test_pool_model_attributes_to_track(self, pool_model: PoolModel):
        """Test generating attribute tracking queries."""
        queries = pool_model.attributesToTrack()

        assert isinstance(queries, list)
        assert len(queries) > 0

        # Each query should have objnam and keys
        for query in queries:
            assert "objnam" in query
            assert "keys" in query
            assert isinstance(query["keys"], list)

    def test_pool_model_add_existing_object_updates(
        self, pool_model: PoolModel, pool_model_data
    ):
        """Test adding an object that already exists updates it."""
        original_count = pool_model.numObjects

        # Add same object with different attributes
        obj = pool_model.addObject(
            "LIGHT1",
            {
                OBJTYP_ATTR: CIRCUIT_TYPE,
                SUBTYP_ATTR: "INTELLI",
                SNAME_ATTR: "Updated Light Name",
                STATUS_ATTR: "ON",
            },
        )

        # Should return existing object updated
        assert obj.objnam == "LIGHT1"
        assert obj.sname == "Updated Light Name"
        assert pool_model.numObjects == original_count  # Count unchanged

    def test_pool_model_ignore_unknown_types(self):
        """Test that objects with untracked types are not added."""
        # Create model with limited attribute map
        model = PoolModel(attributeMap={CIRCUIT_TYPE: {STATUS_ATTR}})

        # Try to add a PUMP (not in attribute map)
        obj = model.addObject(
            "PUMP1",
            {
                OBJTYP_ATTR: PUMP_TYPE,
                SUBTYP_ATTR: "VS",
                SNAME_ATTR: "Pool Pump",
                STATUS_ATTR: "10",
            },
        )

        assert obj is None
        assert model.numObjects == 0
