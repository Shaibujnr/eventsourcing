from functools import reduce

import six

from eventsourcing.domain.model.entity import EventSourcedEntity
from eventsourcing.domain.model.snapshot import take_snapshot
from eventsourcing.domain.services.snapshot import get_snapshot
from eventsourcing.infrastructure.event_store import EventStore
from eventsourcing.infrastructure.stored_events.transcoders import deserialize_domain_entity, make_stored_entity_id


class EventPlayer(object):

    def __init__(self, event_store, entity_id_prefix, mutate_method):
        assert isinstance(event_store, EventStore), event_store
        self.event_store = event_store
        self.entity_id_prefix = entity_id_prefix
        self.mutate = mutate_method

    def replay_events(self, entity_id):
        # Make the stored entity ID.
        stored_entity_id = make_stored_entity_id(self.entity_id_prefix, entity_id)

        # Get snapshot, if exists.
        snapshot = get_snapshot(stored_entity_id, self.event_store)

        # Mutate entity state according to the sequence of domain events.
        start_state = None if snapshot is None else entity_from_snapshot(snapshot)

        # Hold on to the version of the initial state.
        start_version = 0 if start_state is None else start_state._version

        # Get entity's domain events from event store.
        since = snapshot.last_event_id if snapshot else None
        domain_events = self.event_store.get_entity_events(stored_entity_id, since=since)

        # Get the entity by a left fold of the domain events over the initial state.
        domain_entity = reduce(self.mutate, domain_events, start_state)

        # Create a snapshot if that was becoming too many events to load for this type.
        if domain_entity is not None:
            assert isinstance(domain_entity, EventSourcedEntity)
            snapshot_threshold = domain_entity.__snapshot_threshold__
            if snapshot_threshold is not None:
                assert isinstance(snapshot_threshold, six.integer_types)
                version_difference = domain_entity._version - start_version
                if version_difference > snapshot_threshold:
                    take_snapshot(domain_entity)

        # Return the domain entity.
        return domain_entity


def entity_from_snapshot(snapshot):
    return deserialize_domain_entity(snapshot.topic, snapshot.attrs)
