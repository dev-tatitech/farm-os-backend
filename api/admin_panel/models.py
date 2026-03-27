from django.db import models

class Species(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)

class Breed(models.Model):
    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name="breeds")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    
class UnitType(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)