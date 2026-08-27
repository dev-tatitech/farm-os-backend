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
