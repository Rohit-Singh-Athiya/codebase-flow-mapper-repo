# Libraries, CLIs, mobile apps, and anything unclassified

## Library / SDK
- **Public API surface:** `exports`/`main`/`index` files, type definitions, docs and examples. This is the contract; internals are secondary.
- **Internals:** how the public API delegates to internal modules; extension points (plugins, hooks).
- **Build and release:** bundler/compiler, targets, versioning, publish workflow.
- Diagrams: L0 consumer → library → dependencies; L1 public API → internal modules; L2 a typical call path, and the release pipeline.

## CLI tool
- **Command tree:** top-level command → subcommands → handlers (read the arg parser setup). Config loading, output format, exit codes.
- Diagrams: L1 command tree; L2 one command's execution from argv to output.

## Mobile app
- **Navigation graph and screens, state, networking layer, native modules, build variants/flavors, release pipeline** (Fastlane/Gradle/Xcode).
- Diagrams: L1 screen/navigation map plus layers; L2 launch → auth → main flow.

## Unclassified or tiny repo
Say plainly what it is. A simple repo deserves a simple page: one level-0, one level-1, one level-2 flow is enough. Resist inventing architecture to fill space; list unknowns in `open_questions`.
