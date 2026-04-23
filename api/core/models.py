from django.db import models

class TimeStampedModel(models.Model):

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        
class GroupType(models.Model):
    user = models.ForeignKey("account.User", null=True, blank=True, on_delete=models.SET_NULL, related_name='group_type')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class EventType(models.Model):
    user = models.ForeignKey("account.User", null=True, blank=True, on_delete=models.SET_NULL, related_name='event_type')
    name = models.CharField(max_length=100, unique=True)           
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["name"]
        

    def __str__(self):
        return self.name