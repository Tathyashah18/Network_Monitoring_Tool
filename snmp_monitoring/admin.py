from django.contrib import admin

from .models import (
    SNMPDeviceInfo,
    SNMPCPUHistory,
    SNMPMemoryHistory,
    SNMPDiskHistory,
)


@admin.register(SNMPDeviceInfo)
class SNMPDeviceInfoAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "hostname",
        "snmp_status",
        "last_updated",
    )

    list_filter = (
        "snmp_status",
    )

    search_fields = (
        "device__ip_address",
        "hostname",
        "object_id",
    )

    readonly_fields = (
        "last_updated",
    )


@admin.register(SNMPCPUHistory)
class SNMPCPUHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "utilization",
        "timestamp",
    )

    list_filter = (
        "device",
    )

    search_fields = (
        "device__ip_address",
    )

    ordering = (
        "-timestamp",
    )


@admin.register(SNMPMemoryHistory)
class SNMPMemoryHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "utilization",
        "total",
        "used",
        "available",
        "timestamp",
    )

    list_filter = (
        "device",
    )

    search_fields = (
        "device__ip_address",
    )

    ordering = (
        "-timestamp",
    )


@admin.register(SNMPDiskHistory)
class SNMPDiskHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "disk_name",
        "utilization",
        "total",
        "used",
        "available",
        "timestamp",
    )

    list_filter = (
        "device",
        "disk_name",
    )

    search_fields = (
        "device__ip_address",
        "disk_name",
    )

    ordering = (
        "-timestamp",
    )