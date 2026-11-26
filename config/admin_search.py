from django.contrib.admin.utils import get_fields_from_path
from django.contrib.admin.views.main import ChangeList
from django.utils.text import capfirst


SEARCH_COLUMN = "search_column"


class SearchColumnChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filters = super().get_filters_params(params)
        filters.pop(SEARCH_COLUMN, None)
        return filters


class SearchColumnsAdminMixin:
    def get_changelist(self, request, **kwargs):
        return SearchColumnChangeList

    def get_search_fields(self, request):
        fields = super().get_search_fields(request)
        selected = request.GET.get(SEARCH_COLUMN, "")
        return (selected,) if selected in fields else fields

    def search_columns(self):
        return [
            (name, " · ".join(capfirst(str(field.verbose_name)) for field in
                              get_fields_from_path(self.model, name)))
            for name in self.search_fields
        ]
