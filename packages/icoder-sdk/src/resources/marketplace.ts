/** Marketplace API resource — agent discovery, download, install. */

import type { AxiosInstance } from 'axios';

export interface MarketplacePackage {
  id: string; name: string; version: string; description: string;
  category: string; icon: string; agent_type: string;
  publisher_name: string; expert_count: number; tool_count: number;
  downloads: number; published_at: string; integrity?: { sha256: string };
}

export class MarketplaceResource {
  constructor(private http: AxiosInstance) {}

  list(search = '', category = '', sort = 'newest', limit = 50) {
    return this.http.get<{ packages: MarketplacePackage[]; total: number }>(
      '/api/marketplace/packages', { params: { search, category, sort, limit } }
    );
  }

  get(pkgId: string) {
    return this.http.get<MarketplacePackage>(`/api/marketplace/packages/${encodeURIComponent(pkgId)}`);
  }

  download(pkgId: string) {
    return this.http.get(`/api/marketplace/packages/${encodeURIComponent(pkgId)}/download`);
  }

  install(pkgId: string) {
    return this.http.post(`/api/marketplace/packages/${encodeURIComponent(pkgId)}/install`);
  }

  stats() { return this.http.get('/api/marketplace/stats'); }
  categories() { return this.http.get('/api/marketplace/packages/categories'); }
  installed() { return this.http.get('/api/marketplace/installed'); }
}
