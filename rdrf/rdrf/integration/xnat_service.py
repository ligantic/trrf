import openapi_client
from django.conf import settings
from django.utils.translation import gettext as _
from openapi_client import ApiException


def xnat_api_client():
    return openapi_client.ApiClient(
        openapi_client.Configuration(
            host=settings.XNAT_API_ENDPOINT,
            username=settings.XNAT_API_USERNAME,
            password=settings.XNAT_API_PASSWORD,
        )
    )


class XnatApiException(ApiException):
    pass


class XnatApi:
    def __init__(self, api_instance):
        self._api_instance = api_instance

    def authenticate(self):
        try:
            self._api_instance.data_services_auth_put()
        except openapi_client.ApiException as e:
            auth_cookie = e.headers.get("Set-Cookie", "x")
            return auth_cookie

    def get_experiments(self, project_id, subject_id):
        try:
            api_response = self._api_instance.data_projects_project_id_subjects_subject_id_experiments_get(
                project_id=project_id,
                subject_id=subject_id,
                format="json",
            )

        except ApiException as e:
            if e.status == 404:
                raise XnatApiException(
                    e.status, reason=_("Invalid Project or Subject ID.")
                )

        result_set = api_response.result_set

        return [
            {
                "date": result.insert_date,
                "id": result.id,
                "label": result.label,
                "URI": result.uri,
            }
            for result in result_set.result
        ]

    def get_scans(self, experiment_id):
        api_response = (
            self._api_instance.data_experiments_experiment_id_scans_get(
                experiment_id=experiment_id,
                format="json",
            )
        )
        result_set = api_response.result_set
        return [
            {
                "id": result.id,
                "type": result.type,
                "series_description": result.series_description,
                "URI": result.uri,
            }
            for result in result_set.result
        ]


def xnat_experiments_scans(project_id, subject_id):
    with xnat_api_client() as api_client:
        api_instance = openapi_client.DefaultApi(api_client)

        xnat_api = XnatApi(api_instance)
        api_client.cookie = xnat_api.authenticate()

        return [
            {**experiment, "scans": xnat_api.get_scans(experiment.get("id"))}
            for experiment in xnat_api.get_experiments(project_id, subject_id)
        ]
