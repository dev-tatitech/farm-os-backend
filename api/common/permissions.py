class Permissions:
    class Farm:
        CREATE = "create_farm"
        UPDATE = "update_farm"
        DELETE = "delete_farm"
        
    class FarmUnit:
        CREATE = "create_farm_unit"
        UPDATE = "update_farm_unit"
        DELETE = "delete_farm_unit"
        VIEW = "view_farm_unit"

    class Animal:
        CREATE = "add_animal_details"
        UPDATE = "update_animal_details"
        DELETE = "delete_animal_details"
        VIEW = "view_animal_details"
    class Production:
        CREATE = "add_production"
        UPDATE = "update_production"
        DELETE = "delete_production"
        VIEW = "view_production"

    class Reproduction:
        CREATE = "add_reproduction"
        UPDATE = "update_reproduction"
        DELETE = "delete_reproduction"
        VIEW = "view_reproduction"
        RESTRICTION_OVERRIDE = "reproduction_restriction_override"

    class Health:
        CREATE = "add_health"
        UPDATE = "update_health"
        DELETE = "delete_health"
        VIEW = "view_health"

    class Feed:
        CREATE = "add_feed"
        UPDATE = "update_feed"
        DELETE = "delete_feed"
        VIEW = "view_feed"

    class MovementRecord:
        CREATE = "add_movement_record"
        UPDATE = "update_movement_record"
        DELETE = "delete_movement_record"
        VIEW = "view_movement_record"

    class SalesRecord:
        CREATE = "add_sales_record"
        UPDATE = "update_sales_record"
        DELETE = "delete_sales_record"
        VIEW = "view_sales_record"
        RESTRICTION_OVERRIDE = "sale_restriction_override"

    class Finance:
        CREATE = "add_finance"
        UPDATE = "update_finance"
        DELETE = "delete_finance"
        VIEW = "view_finance"

    class Pharmacy:
        CREATE = "add_pharmacy"
        UPDATE = "update_pharmacy"
        DELETE = "delete_pharmacy"
        VIEW = "view_pharmacy"
        EXTERNAL_OVERRIDE = "external_medication_override"

    class Reports:
        LIVESTOCK_DASHBOARD = "view_livestock_dashboard"
        REPORTS = "view_reports"