from app.models import AuditEvent

def audit(db, actor, action, entity_type, entity_id, before=None, after=None):
    db.add(AuditEvent(actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
                      entity_id=str(entity_id), before_json=before, after_json=after))