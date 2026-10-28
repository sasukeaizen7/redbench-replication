| § | Claim | Paper | Replication | Verdict |
|---|---|---|---|---|
| Table 4 | redset: QRR_DML | 0.72 | 0.72 | confirmed |
| Table 4 | redset: QRR | 0.73 | 0.73 | confirmed |
| Table 4 | redset: SRR_DML | 0.86 | 0.86 | confirmed |
| Table 4 | redset: SRR | 0.87 | 0.86 | confirmed |
| Table 4 | generation: QRR_DML | 0.73 | 0.74 | close |
| Table 4 | generation: QRR | 0.79 | 0.80 | close |
| Table 4 | generation: SRR_DML | 0.95 | 0.96 | confirmed |
| Table 4 | generation: SRR | 0.98 | 0.99 | confirmed |
| Table 4 | matching: QRR_DML | 0.97 | 0.97 | confirmed |
| Table 4 | matching: QRR | 0.98 | 0.98 | confirmed |
| Table 4 | matching: SRR_DML | 0.99 | 0.99 | confirmed |
| Table 4 | matching: SRR | 0.99 | 1.00 | confirmed |
| Table 4 | baseline_round_robin: QRR_DML | 0.00 | 0.00 | confirmed |
| Table 4 | baseline_round_robin: QRR | 0.74 | 0.74 | confirmed |
| Table 4 | baseline_round_robin: SRR_DML | 0.36 | 0.36 | confirmed |
| Table 4 | baseline_round_robin: SRR | 0.99 | 1.00 | confirmed |
| §5.2 | Cluster 186/8: queries | 36,000 | 36,353 | confirmed |
| §5.2 | Cluster 186/8: selects | 25,000 | 24,881 | confirmed |
| §5.2 | Cluster 186/8: distinct selects | 6,400 | 6,405 | confirmed |
| §5.2 | Cluster 186/8: DML | 11,000 | 11,472 | confirmed |
| Table 5 | Matching: string filter share | 67% | 69% | close |
| Table 5 | Generation: string filter share | 75% | 76% | close |
| §4.1 | Selects among queries (provisioned) | 50% | 31% | not |
| §4.3 | INSERTs among queries (provisioned) | 20% | 16% | close |
| §4.3 | INSERT is the largest DML type (provisioned) | insert | delete (20% of queries) | not |
| §4.1 | Selects among queries (serverless) | 50% | 31% | not |
| §4.3 | INSERTs among queries (serverless) | 20% | 36% | not |
| §4.3 | INSERT is the largest DML type (serverless) | insert | insert (36% of queries) | confirmed |
| §4.3 | Most INSERTs are INSERT ... SELECT (provisioned) | > 50% | 54% | confirmed |
| §4.3 | Most INSERTs are INSERT ... SELECT (serverless) | > 50% | 28% | not |
| §2.1 | CPU share of the top 0.1 % of queries (provisioned) | 25% | 51% | close |
| §2.1 | CPU share of the top 0.1 % of queries (serverless) | 25% | 39% | close |
| §6 (Fig 8) | baseline_round_robin: caching speedup | 1.00-1.08x | 1.00x (DuckDB, simulated result cache) | confirmed |
| §6 (Fig 8) | matching: caching speedup | 2.12-2.98x | 18.61x (DuckDB, simulated result cache) | close |
| §6 | Caching helps matching, not the round-robin baseline | yes | 18.61x vs 1.00x | confirmed |
