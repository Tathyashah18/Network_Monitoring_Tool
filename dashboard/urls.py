from django.urls import path

from . import views


urlpatterns = [

    path(
        "",
        views.dashboard,
        name="dashboard"
    ),

    path(
        "logs/",
        views.device_logs,
        name="device_logs"
    ),

    path(
        "scan/",
        views.run_scanner,
        name="run_scanner"
    ),

    path(
        "device/<str:ip>/",
        views.device_detail,
        name="device_detail"
    ),

    # Live device detail API
    path(
        "device/<str:ip>/api/",
        views.device_detail_api,
        name="device_detail_api"
    ),

    path(
        "api/devices/",
        views.device_status_api,
        name="device_status_api"
    ),
    path(
    "topology/",
    views.open_topology,
    name="open_topology"
    ),
    path(
    "api/topology/status/",
    views.topology_status_api,
    name="topology_status_api"
    ),
    # Request Remote Access
    path(
        "request-remote-access/<str:ip>/",
        views.request_remote_access,
        name="request_remote_access"
    ),
]