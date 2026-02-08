from django.conf import settings
from django.db import models
from django.utils import timezone


class AlertSeverity(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class AlertStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    RESOLVED = 'resolved', 'Resolved'


class TemperatureAlert(models.Model):
    """Temperature alerts for storage rooms"""
    room = models.ForeignKey('inventory.StorageRoom', on_delete=models.CASCADE, related_name='temperature_alerts')
    temperature = models.DecimalField(max_digits=5, decimal_places=2)
    severity = models.CharField(max_length=20, choices=AlertSeverity.choices, default=AlertSeverity.MEDIUM)
    status = models.CharField(max_length=20, choices=AlertStatus.choices, default=AlertStatus.ACTIVE)
    message = models.TextField(blank=True)
    
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='acknowledged_alerts'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    action_taken = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['room', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self) -> str:
        return f"Alert: {self.room.room_name} - {self.temperature}°C ({self.severity})"

    def acknowledge(self, user):
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()

    def resolve(self, action_taken: str = ''):
        self.status = AlertStatus.RESOLVED
        self.resolved_at = timezone.now()
        self.action_taken = action_taken
        self.save()


class TemperatureLog(models.Model):
    """Historical temperature readings"""
    room = models.ForeignKey('inventory.StorageRoom', on_delete=models.CASCADE, related_name='temperature_logs')
    logged_at = models.DateTimeField()
    temperature = models.DecimalField(max_digits=6, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='temperature_logs')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-logged_at']
        indexes = [
            models.Index(fields=['room', '-logged_at']),
        ]

    def __str__(self) -> str:
        return f"{self.room.room_name} - {self.logged_at}: {self.temperature}°C"
