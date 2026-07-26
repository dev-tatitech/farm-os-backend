from ninja import Router
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from account.auth import get_current_user
from account.models import User as users
from organization.models import Farm
from animals.models import Animal, AnimalGroup
from movement_records.models import SalesRecord
from common.permission_checker import user_has_permission
from common.permissions import Permissions

from .models import Transaction, TransactionCategory
from .services import seed_transaction_categories, compute_cost_breakdown, compute_total_cost_to_date, compute_income_generated
from .schema import ListResponseSchema, APIResponse, TransactionSchemaIn

router = Router(tags=["Finance"])


@router.post("/transaction-category/seed/", response={200: APIResponse, 403: APIResponse})
def seed_categories(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    created = seed_transaction_categories()
    return 200, APIResponse(
        success=True, message="Transaction categories seeded successfully", data={"created": created}
    )


@router.get("/transaction-category/", response={200: APIResponse, 403: APIResponse})
def get_transaction_categories(request, type: str = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    qs = TransactionCategory.objects.filter(is_active=True)
    if type:
        qs = qs.filter(type=type)
    data = list(qs.values("id", "name", "type", "is_system"))
    return 200, APIResponse(success=True, message="Transaction categories", data=data)


@router.post("/transaction/", response={200: APIResponse, 403: APIResponse})
def create_transaction(request, payload: TransactionSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Finance.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    category = get_object_or_404(TransactionCategory, id=payload.category_id, type=payload.type, is_active=True)

    animal = None
    if payload.animal_id:
        animal = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
    group = None
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id=payload.group_id, farm=farm)

    txn = Transaction.objects.create(
        farm=farm,
        animal=animal,
        group=group,
        type=payload.type,
        category=category,
        amount=payload.amount,
        currency=payload.currency,
        transaction_date=payload.transaction_date,
        description=payload.description or "",
        source_module="manual",
        payment_status=payload.payment_status,
        payment_method=payload.payment_method,
        transaction_reference=payload.transaction_reference,
        notes=payload.notes,
        created_by=user,
    )
    return 200, APIResponse(
        success=True,
        message="Transaction recorded successfully",
        data={"id": txn.id, "type": txn.type, "amount": txn.amount, "category": category.name},
    )


@router.get(
    "/transaction/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_transactions(
    request, page: int, page_size: int, farm_id: int,
    animal_id: int = None, group_id: int = None, type: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Finance.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = Transaction.objects.select_related("category", "animal", "group").filter(farm=farm)
    if animal_id:
        qs = qs.filter(animal_id=animal_id)
    if group_id:
        qs = qs.filter(group_id=group_id)
    if type:
        qs = qs.filter(type=type)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": t.id,
            "type": t.type,
            "category": t.category.name,
            "amount": t.amount,
            "currency": t.currency,
            "transaction_date": t.transaction_date,
            "description": t.description,
            "source_module": t.source_module,
            "animal_id": t.animal_id,
            "animal_tag": t.animal.tag_id if t.animal else None,
            "group_id": t.group_id,
            "group_name": t.group.name if t.group else None,
            "payment_status": t.payment_status,
            "payment_method": t.payment_method,
            "transaction_reference": t.transaction_reference,
            "notes": t.notes,
            "created_at": t.created_at,
        }
        for t in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True,
        message="transactions fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get("/animal-financial-summary/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def animal_financial_summary(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)

    cost_by_category = compute_cost_breakdown(animal)
    total_cost = compute_total_cost_to_date(animal)
    total_income = compute_income_generated(animal)
    acquisition_or_opening_value = float(animal.acquisition_cost or animal.opening_value or 0)

    # A completed sale is authoritative over a manually-set estimate — once an
    # animal is actually sold, the profile should reflect what it sold for,
    # not a pre-sale guess.
    completed_sale = SalesRecord.objects.filter(animal=animal).order_by("-created_at").first()
    sale_price = float(completed_sale.price) if completed_sale else None
    estimated_current_value = float(animal.current_estimated_value) if animal.current_estimated_value else None
    sale_value_for_profit = sale_price if sale_price is not None else estimated_current_value

    data = {
        "animal_id": animal.id,
        "tag_id": animal.tag_id,
        "acquisition_or_opening_value": acquisition_or_opening_value,
        "cost_breakdown": cost_by_category,
        "total_cost_to_date": total_cost,
        "income_generated": total_income,
        "is_sold": completed_sale is not None,
        "sale_price": sale_price,
        "sale_date": completed_sale.sale_date if completed_sale else None,
        "estimated_current_value": estimated_current_value,
        "estimated_profit_or_loss": (
            sale_value_for_profit + total_income - total_cost
            if sale_value_for_profit is not None
            else None
        ),
    }
    return 200, APIResponse(success=True, message="Animal financial summary", data=data)


@router.get("/animal-cost-timeline/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def animal_cost_timeline(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)

    txns = Transaction.objects.filter(animal=animal).select_related("category", "created_by").order_by("-transaction_date")
    data = [
        {
            "date": t.transaction_date,
            "type": t.type,
            "category": t.category.name,
            "description": t.description,
            "amount": t.amount,
            "source_module": t.source_module,
            "recorded_by": t.created_by.email if t.created_by else None,
            "transaction_reference": t.transaction_reference,
        }
        for t in txns
    ]
    return 200, APIResponse(success=True, message="Animal cost timeline", data=data)
