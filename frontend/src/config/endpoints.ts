import type { EndpointConfig, EndpointField } from "../types/api";

const PAGE_FIELD: EndpointField = {
  key: "page",
  label: "Page",
  in: "query",
  type: "number",
  defaultValue: "1",
};

const SIZE_FIELD: EndpointField = {
  key: "size",
  label: "Size",
  in: "query",
  type: "number",
  defaultValue: "50",
};

const CATEGORY_FIELD: EndpointField = {
  key: "category",
  label: "Category",
  in: "query",
  type: "text",
  placeholder: "actor",
};

function paginationFields(): EndpointField[] {
  return [{ ...PAGE_FIELD }, { ...SIZE_FIELD }];
}

export const endpointConfigs: EndpointConfig[] = [
  {
    id: "api-ping",
    title: "API Ping",
    method: "GET",
    path: "/api",
    description: "Check API status and build metadata.",
    fields: [],
  },
  {
    id: "ingest",
    title: "Trigger Ingest",
    method: "POST",
    path: "/api/ingest",
    description: "Schedule ingest for all datasets or selected ones.",
    fields: [
      {
        key: "data_set",
        label: "Datasets (comma-separated)",
        in: "body",
        type: "list",
        placeholder: "title.basics.tsv,title.ratings.tsv",
      },
    ],
  },
  {
    id: "import-tasks",
    title: "Import Tasks",
    method: "GET",
    path: "/api/import-tasks",
    description: "List ingest task history.",
    fields: [...paginationFields()],
  },
  {
    id: "stats",
    title: "Stats",
    method: "GET",
    path: "/api/stats",
    description: "Get indexed dataset and disk usage stats.",
    fields: [],
  },
  {
    id: "titles-list",
    title: "List Titles",
    method: "GET",
    path: "/api/titles",
    description: "Paginated titles with optional filters.",
    fields: [
      {
        key: "tconst",
        label: "tconst (comma-separated)",
        in: "query",
        type: "list",
        placeholder: "tt0111161,tt0068646",
      },
      {
        key: "genre",
        label: "Genre",
        in: "query",
        type: "text",
        placeholder: "Drama",
      },
      { key: "year_from", label: "Year From", in: "query", type: "number" },
      {
        key: "min_rating",
        label: "Min Rating",
        in: "query",
        type: "number",
        placeholder: "7.5",
      },
      {
        key: "title_type",
        label: "Title Type",
        in: "query",
        type: "text",
        placeholder: "movie",
      },
      ...paginationFields(),
    ],
  },
  {
    id: "title-detail",
    title: "Get Title",
    method: "GET",
    path: "/api/titles/:tconst",
    description: "Get one title by tconst.",
    fields: [
      {
        key: "tconst",
        label: "tconst",
        in: "path",
        type: "text",
        required: true,
        placeholder: "tt0111161",
      },
    ],
  },
  {
    id: "title-principals",
    title: "Title Principals",
    method: "GET",
    path: "/api/titles/:tconst/principals",
    description: "List principals for one title.",
    fields: [
      {
        key: "tconst",
        label: "tconst",
        in: "path",
        type: "text",
        required: true,
        placeholder: "tt0111161",
      },
      { ...CATEGORY_FIELD },
      ...paginationFields(),
    ],
  },
  {
    id: "person-detail",
    title: "Get Person",
    method: "GET",
    path: "/api/people/:nconst",
    description: "Get one person by nconst.",
    fields: [
      {
        key: "nconst",
        label: "nconst",
        in: "path",
        type: "text",
        required: true,
        placeholder: "nm0000209",
      },
    ],
  },
  {
    id: "person-credits",
    title: "Person Credits",
    method: "GET",
    path: "/api/people/:nconst/credits",
    description: "List credits for one person.",
    fields: [
      {
        key: "nconst",
        label: "nconst",
        in: "path",
        type: "text",
        required: true,
        placeholder: "nm0000209",
      },
      { ...CATEGORY_FIELD },
      ...paginationFields(),
    ],
  },
  {
    id: "series-episodes",
    title: "Series Episodes",
    method: "GET",
    path: "/api/series/:tconst/episodes",
    description: "List episodes for a series.",
    fields: [
      {
        key: "tconst",
        label: "Series tconst",
        in: "path",
        type: "text",
        required: true,
        placeholder: "tt0944947",
      },
      {
        key: "season_number",
        label: "Season Number",
        in: "query",
        type: "number",
      },
    ],
  },
  {
    id: "search-titles",
    title: "Search Titles",
    method: "GET",
    path: "/api/search/titles",
    description: "Search titles by query.",
    fields: [
      {
        key: "q",
        label: "Query",
        in: "query",
        type: "text",
        required: true,
        placeholder: "matrix",
      },
      {
        key: "title_type",
        label: "Title Type",
        in: "query",
        type: "text",
        placeholder: "movie",
      },
      { key: "year_from", label: "Year From", in: "query", type: "number" },
      ...paginationFields(),
    ],
  },
  {
    id: "search-people",
    title: "Search People",
    method: "GET",
    path: "/api/search/people",
    description: "Search people by name query.",
    fields: [
      {
        key: "q",
        label: "Query",
        in: "query",
        type: "text",
        required: true,
        placeholder: "keanu",
      },
      ...paginationFields(),
    ],
  },
];
