def log_audit(*, user, action, source_module, object_type=None, object_id=None,
               previous_value=None, new_value=None, reason=None):
    from .models import AuditLog

    return AuditLog.objects.create(
        user=user, action=action, source_module=source_module,
        object_type=object_type, object_id=str(object_id) if object_id is not None else None,
        previous_value=str(previous_value) if previous_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        reason=reason,
    )


def security_event(action, actor, *, target=None, org=None, farm=None, previous=None, new=None):
    import json
    from .models import AuditLog

    return AuditLog.objects.create(
        user=actor, action=action, source_module="domain01",
        object_type=target._meta.label_lower if target is not None else None,
        object_id=str(target.pk) if target is not None else None,
        previous_value=json.dumps(previous, default=str) if previous is not None else None,
        new_value=json.dumps(new, default=str) if new is not None else None,
        context={"organization_id": str(org.pk) if org else None,
                 "farm_id": farm.pk if farm else None, "result": "success", "source": "api"},
    )
