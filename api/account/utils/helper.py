from ninja.errors import HttpError
from ..models import Beneficiary
from django.db.models import Q


def resolve_fk(model, id_value, field_name):
    if not id_value:
        return None
    try:
        return model.objects.get(id=id_value)
    except model.DoesNotExist:
        raise HttpError(400, f"Invalid {field_name}")


def get_filtered_beneficiaries(
    beneficiary_filter,
    beneficiaries_filter_id,
    selected_gender,
    selected_religion,
    selected_marital,
    currentOrganization,
    tribe,
):
    qs = (
        Beneficiary.objects.select_related(
            "region",
            "stateOrigin",
            "lgaOrigin",
            "batch",
            "added_by",
            "currentOrganization",
            "tribe",
        )
        .prefetch_related("distribute")
        .all()
    )

    filters = Q()
    if beneficiary_filter != "All":
        if beneficiary_filter == "Batch":
            filters &= Q(batch_id=beneficiaries_filter_id)
        elif beneficiary_filter == "Region":
            filters &= Q(region_id=beneficiaries_filter_id)
        elif beneficiary_filter == "State":
            filters &= Q(stateOrigin_id=beneficiaries_filter_id)
        elif beneficiary_filter == "LGA":
            filters &= Q(lgaOrigin_id=beneficiaries_filter_id)
    if selected_gender != "All":
        filters &= Q(gender=selected_gender)

    if selected_religion != "All":
        filters &= Q(religion=selected_religion)

    if selected_marital != "All":
        filters &= Q(maritalStatus=selected_marital)

    if currentOrganization is not None:
        filters &= Q(currentOrganization_id=currentOrganization)

    if tribe is not None:
        filters &= Q(tribe_id=tribe)

    return qs.filter(filters)


def json_validations(data_dict, value):
    return next((k for k, v in data_dict.items() if v == value), None)
