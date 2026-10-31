from django.db import models

from dashboard.models import Device


# ============================================================
# SNMP DEVICE INFORMATION
# ============================================================

class SNMPDeviceInfo(models.Model):

    device = models.OneToOneField(
        Device,
        on_delete=models.CASCADE,
        related_name="snmp_info"
    )

    hostname = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    system_description = models.TextField(
        blank=True,
        null=True
    )

    system_uptime = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    object_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    snmp_status = models.CharField(
        max_length=20,
        default="DOWN"
    )

    last_updated = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):

        return (
            f"SNMP - "
            f"{self.device.ip_address}"
        )


# ============================================================
# CPU HISTORY
# ============================================================

class SNMPCPUHistory(models.Model):

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="snmp_cpu_history"
    )

    utilization = models.FloatField()

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = [
            "timestamp"
        ]

    def __str__(self):

        return (
            f"{self.device.ip_address} - "
            f"CPU {self.utilization:.2f}%"
        )


# ============================================================
# MEMORY HISTORY
# ============================================================

class SNMPMemoryHistory(models.Model):

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="snmp_memory_history"
    )

    total = models.PositiveBigIntegerField()

    used = models.PositiveBigIntegerField()

    available = models.PositiveBigIntegerField()

    utilization = models.FloatField()

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = [
            "timestamp"
        ]

    def __str__(self):

        return (
            f"{self.device.ip_address} - "
            f"Memory {self.utilization:.2f}%"
        )


# ============================================================
# DISK HISTORY
# ============================================================

class SNMPDiskHistory(models.Model):

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="snmp_disk_history"
    )

    disk_name = models.CharField(
        max_length=255
    )

    total = models.PositiveBigIntegerField()

    used = models.PositiveBigIntegerField()

    available = models.PositiveBigIntegerField()

    utilization = models.FloatField()

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = [
            "timestamp"
        ]

    def __str__(self):

        return (
            f"{self.device.ip_address} - "
            f"{self.disk_name} - "
            f"{self.utilization:.2f}%"
        )