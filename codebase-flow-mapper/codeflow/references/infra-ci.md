# Mapping infrastructure, deployment and CI/CD

## What to establish
- **Tooling:** Terraform/Pulumi/CloudFormation/Helm/Kustomize/Ansible/Serverless.
- **Structure:** modules vs. environments (`envs/prod`, `stacks/`), how state is stored (backend config; don't copy secrets), how environments differ.
- **Resources:** group by purpose (network, compute, data, identity, observability) instead of listing everything.
- **Pipelines:** each CI workflow's trigger, jobs, order, gates (approvals, tests), artifacts, and deploy targets. The workflow YAML is the source of truth.
- **Secrets and config:** *where* they come from (vault, CI secrets, parameter store). Names only, never values.
- **Release flow:** branching strategy, tagging, rollback path if documented.

## Diagrams to produce
- **L0:** repo → CI → environments (dev/staging/prod) → cloud accounts/regions.
- **L1:** resource groups and their dependencies (network → compute → data), or module graph.
- **L2:** *the deploy pipeline* as a flowchart with gates, or *a change's path from PR to production*.

## Where to look
`.github/workflows/`, `Jenkinsfile`, `terraform/`, `modules/`, `helm/`, `k8s/`, `Dockerfile*`, `Makefile`, `scripts/deploy*`.

## Common traps
Reusable workflows/composite actions hide steps in other files, so follow `uses:` links within the repo. Mark anything provisioned elsewhere as an external boundary.
