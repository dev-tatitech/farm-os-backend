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

    class Reproduction:
        CREATE = "add_reproduction"
        UPDATE = "update_reproduction"
        DELETE = "delete_reproduction"
        VIEW = "view_reproduction"
