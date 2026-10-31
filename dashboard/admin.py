from django.contrib import admin
from .models import Device, DeviceLog


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ip_address",
        "hostname",
        "mac_address",
        "status",
        "last_seen",
    )

    list_filter = (
        "status",
    )

    search_fields = (
        "ip_address",
        "hostname",
        "mac_address",
    )

    ordering = (
        "ip_address",
    )


@admin.register(DeviceLog)
class DeviceLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "status",
        "timestamp",
    )

    list_filter = (
        "status",
        "timestamp",
    )

    search_fields = (
        "device__ip_address",
    )

    ordering = (
        "-timestamp",
    )