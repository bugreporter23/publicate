# Design through integration

Some software boundaries become clear only when a complete system is assembled.
A component can have a plausible interface in isolation and still put the wrong
responsibilities on its callers. Integration makes those decisions concrete:
which component owns configuration, where state persists, how failures propagate,
and what a deployment actually requires.

An integration workspace gives that investigation room to proceed. It can combine
published releases with private components and locally modified source. An
experiment may need an internal test harness, coordinated changes across several
repositories, or a small script tailored to one deployment. Allowing that access
can reveal a useful design before there is a clean interface for expressing it.

The experiment earns its value through what it teaches the constituent projects.
A capability belongs with the component that can maintain it. A recurring need
may justify a new interface; an awkward dependency may suggest a different
division of responsibility. Some glue remains specific to the integration and
stays there. A successful experiment can leave improvements in several projects
and very little permanent integration code.

This approach accepts coupling during exploration and assigns responsibility
when the result is consolidated. Shortcuts carry a cost if downstream software
starts relying on them. Before a component is released, its supported behavior,
dependencies, configuration and compatibility expectations need to be explicit.
The component contract specifies its supported behavior and integration inputs.

Retained version snapshots provide a stable reference. A private integration can start from
a pinned public version and substitute a different implementation at an existing
package, backend or plugin boundary. Recording the baseline and substitutions
makes the experiment understandable and gives it a path back to the released
version. Accepted changes can become another release. Selecting an implementation
for the next build or launch is straightforward; replacing one inside a running
process requires its own state and lifecycle design.

Publication can follow the same separation. A component's public source contains
what consumers need to build and use it. Experiments, private tests and development
records can remain in the workspace that produced it. Published inputs can be
consumed through anonymous fetches, while updates require authorization. Pinned
revisions and content hashes identify the selected source independently of the
workspace's current state.

Publicate supports this publication step by exporting a selected source tree and
checking its declared Nix builds from the standalone source tree. The
integration workspace remains free to investigate the larger system. The release
provides a bounded result that someone else can obtain, understand and compose.
