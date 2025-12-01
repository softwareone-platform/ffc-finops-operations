export type GetDatasourcesByOrganizationIDResponse = [
  {
    id: string; // UUID
    name: string;
    type: string; // e.g., "aws_cnr", "azure_cnr", "azure_tenant"
    parent_id?: string | null; // UUID or null
    resources_charged_this_month: number;
    expenses_so_far_this_month: number;
    expenses_forecast_this_month: number;
  },
];
