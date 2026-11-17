import api from './api';
import type {
  DatasetProfile,
  DatasetProfileSummary,
  ProfilePreflightReport,
  ProfileUsePurpose,
} from '../types/timeseriesProfile';

export const timeseriesProfileApi = {
  listDatasetProfiles: (): Promise<{ success: boolean; items: DatasetProfileSummary[] }> =>
    api.get('/timeseries/profiles/dataset'),

  getDatasetProfile: (
    profileId: string,
    version?: string,
  ): Promise<{ success: boolean; profile: DatasetProfile }> =>
    api.get(`/timeseries/profiles/dataset/${profileId}`, {
      params: version ? { version } : undefined,
    }),

  preflightDatasetProfile: (
    profileId: string,
    usePurpose: ProfileUsePurpose = 'local_validation',
    version?: string,
  ): Promise<{ success: boolean; report: ProfilePreflightReport }> =>
    api.post(
      `/timeseries/profiles/dataset/${profileId}/preflight`,
      { use_purpose: usePurpose },
      { params: version ? { version } : undefined },
    ),
};
