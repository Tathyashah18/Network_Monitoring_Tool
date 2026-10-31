from django.db import models
from django.utils import timezone


# ============================================================
# DEVICE
# ============================================================

class Device(models.Model):

    ip_address = models.GenericIPAddressField(
        unique=True
    )

    hostname = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    mac_address = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        default="Offline"
    )

    # Start of the current online session
    online_since = models.DateTimeField(
        blank=True,
        null=True
    )

    # Uptime of the current/last completed session
    # Stored in seconds
    last_uptime_seconds = models.PositiveIntegerField(
        default=0
    )

    # Last time the device was successfully detected
    last_seen = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            "ip_address"
        ]

    def __str__(self):
        return (
            f"{self.ip_address} - "
            f"{self.status}"
        )

    @property
    def uptime_seconds(self):

        if (
            self.status == "Online"
            and self.online_since
        ):

            elapsed = (
                timezone.now()
                - self.online_since
            ).total_seconds()

            return max(
                0,
                int(elapsed)
            )

        return self.last_uptime_seconds

    @property
    def uptime_display(self):

        total_seconds = self.uptime_seconds

        days = total_seconds // 86400

        remaining = total_seconds % 86400

        hours = remaining // 3600

        remaining %= 3600

        minutes = remaining // 60

        seconds = remaining % 60

        if days > 0:
            return (
                f"{days}d "
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )


# ============================================================
# DEVICE LOG
# ============================================================

class DeviceLog(models.Model):

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="logs"
    )

    status = models.CharField(
        max_length=20
    )

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    message = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = [
            "-timestamp"
        ]

    def __str__(self):
        return (
            f"{self.device.ip_address} - "
            f"{self.status} - "
            f"{self.timestamp}"
        )


# ============================================================
# DEVICE STATISTICS
# ============================================================

class DeviceStats(models.Model):

    device = models.OneToOneField(
        Device,
        on_delete=models.CASCADE,
        related_name="stats"
    )

    # --------------------------------------------------------
    # PING STATISTICS
    # --------------------------------------------------------

    packets_sent = models.PositiveBigIntegerField(
        default=0
    )

    packets_received = models.PositiveBigIntegerField(
        default=0
    )

    packets_lost = models.PositiveBigIntegerField(
        default=0
    )

    # Ping latency in milliseconds
    latency_ms = models.FloatField(
        default=0
    )

    # --------------------------------------------------------
    # LAST MONITORING TIME
    # --------------------------------------------------------

    last_poll_time = models.DateTimeField(
        blank=True,
        null=True
    )

    # --------------------------------------------------------
    # UPDATE TIME
    # --------------------------------------------------------

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"Stats - "
            f"{self.device.ip_address}"
        )


# ============================================================
# DEVICE MONITORING HISTORY
# ============================================================

class DeviceStatsHistory(models.Model):

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="stats_history"
    )

    # Time when this monitoring sample was recorded
    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    # --------------------------------------------------------
    # PING STATISTICS
    # --------------------------------------------------------

    # Ping latency in milliseconds
    latency_ms = models.FloatField(
        default=0
    )

    packets_sent = models.PositiveBigIntegerField(
        default=0
    )

    packets_received = models.PositiveBigIntegerField(
        default=0
    )

    packets_lost = models.PositiveBigIntegerField(
        default=0
    )

    # Packet loss percentage
    packet_loss = models.FloatField(
        default=0
    )

    class Meta:
        ordering = [
            "timestamp"
        ]

    def __str__(self):
        return (
            f"{self.device.ip_address} - "
            f"{self.timestamp}"
        )