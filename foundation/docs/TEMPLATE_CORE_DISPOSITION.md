# Template Core disposition

Manual section 3.16 and both source planes describe `template_core` as a
copy-and-customize plugin scaffold. It demonstrates command handling,
auto-created configuration, and discovery patterns; it is not an AIOS
authoritative reasoning core.

The source implementation writes configuration on initialization and its
manual encourages copying it into the runtime root. Those effects are
intentionally not wired into Viv. The contract remains `retired`, and new
plugins must enter through separately reviewed manifests, trust policy, and
CPU authority boundaries.
