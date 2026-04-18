#!/usr/bin/env python3
# src/mem_graph/agents/map/diagram_agent.py
"""
Mermaid diagram generation agent using pydantic-graph.

Uses a graph-based state machine to drive diagram generation — each node
in the graph represents a stage in the pipeline: classify the request,
gather context, select diagram type, generate, validate, and refine.
Produces syntactically valid Mermaid diagrams for architecture, sequence,
flowchart, ER, state machine, and C4 diagram types.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK

################
#   CONSTANTS
################

_MAX_REFINE_ITERATIONS = 3

logger = logging.getLogger(__name__)


################
#   ENUMS
################


class DiagramType(str, Enum):
    """
    Supported Mermaid diagram types.

    Each type maps to a specific Mermaid syntax and prompt strategy.
    """

    FLOWCHART = "flowchart"
    SEQUENCE = "sequence"
    STATE = "state"
    ER = "er"
    C4_CONTEXT = "c4_context"
    C4_COMPONENT = "c4_component"
    CLASS = "class"
    ARCHITECTURE = "architecture"


################
#   MODELS
################


class DiagramRequest(BaseModel):
    """
    Input specification for a diagram generation run.

    description drives what gets diagrammed.
    diagram_type can be specified or left for the agent to infer.
    context provides additional domain knowledge for accuracy.
    """

    description: str = Field(
        description="What to diagram — feature, system, flow, or relationship."
    )
    diagram_type: DiagramType | None = Field(
        default=None,
        description="Explicit diagram type. If None, the agent infers the best fit.",
    )
    context: str = Field(
        default="",
        description="Additional domain context — existing code, architecture notes, etc.",
    )
    style_hints: list[str] = Field(
        default_factory=list,
        description="Optional style preferences, e.g. 'left to right', 'group by layer'.",
    )


class DiagramOutput(BaseModel):
    """
    Final diagram output with metadata.

    mermaid_source is the raw Mermaid syntax ready to render.
    Includes the inferred or specified diagram type and a brief
    description of what the diagram shows.
    """

    mermaid_source: str = Field(description="Valid Mermaid diagram source code.")
    diagram_type: DiagramType = Field(description="The diagram type that was generated.")
    title: str = Field(description="Short descriptive title for the diagram.")
    description: str = Field(description="One sentence describing what the diagram shows.")
    iterations: int = Field(default=1, description="How many refinement passes were needed.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues noted during generation.",
    )


################
#   GRAPH STATE
################


@dataclass
class DiagramState:
    """
    Mutable state threaded through the diagram generation graph.

    Each graph node reads and writes this state as the pipeline
    progresses from classification through to final output.
    """

    request: DiagramRequest
    inferred_type: DiagramType | None = None
    gathered_context: str = ""
    draft: str = ""
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    iterations: int = 0
    final: DiagramOutput | None = None


################
#   GRAPH NODES
################


@dataclass
class Classify(BaseNode[DiagramState, None, DiagramOutput]):
    """
    Infer the best diagram type from the request description.

    If the request specifies a type explicitly, passes it through.
    Otherwise uses an LLM call to select the most appropriate type
    based on what is being described.
    """

    async def run(self, ctx: GraphRunContext[DiagramState]) -> GatherContext:
        """Classify the request and advance to context gathering."""
        if ctx.state.request.diagram_type is not None:
            ctx.state.inferred_type = ctx.state.request.diagram_type
            return GatherContext()

        inferred = await _infer_diagram_type(ctx.state.request.description)
        ctx.state.inferred_type = inferred
        logger.debug("Inferred diagram type: %s", inferred.value)
        return GatherContext()


@dataclass
class GatherContext(BaseNode[DiagramState, None, DiagramOutput]):
    """
    Assemble all context needed for accurate diagram generation.

    Combines the request description, provided context, style hints,
    and type-specific guidance into a single context block.
    """

    async def run(self, ctx: GraphRunContext[DiagramState]) -> Generate:
        """Assemble context and advance to generation."""
        parts = [ctx.state.request.description]

        if ctx.state.request.context:
            parts.append(f"Additional context:\n{ctx.state.request.context}")

        if ctx.state.request.style_hints:
            hints = ", ".join(ctx.state.request.style_hints)
            parts.append(f"Style preferences: {hints}")

        assert ctx.state.inferred_type is not None

        type_guidance = _type_specific_guidance(ctx.state.inferred_type)
        parts.append(f"Diagram type guidance:\n{type_guidance}")

        ctx.state.gathered_context = "\n\n".join(parts)
        return Generate()


@dataclass
class Generate(BaseNode[DiagramState, None, DiagramOutput]):
    """
    Generate the initial Mermaid diagram draft.

    Calls the diagram generation agent with the assembled context
    and stores the raw Mermaid source as the current draft.
    """

    async def run(self, ctx: GraphRunContext[DiagramState]) -> Validate:
        """Generate draft and advance to validation."""
        ctx.state.iterations += 1
        assert ctx.state.inferred_type is not None
        draft = await _generate_diagram(
            ctx.state.gathered_context,
            ctx.state.inferred_type,
            ctx.state.validation_errors,
        )
        ctx.state.draft = draft
        ctx.state.validation_errors = []
        return Validate()


@dataclass
class Validate(BaseNode[DiagramState, None, DiagramOutput]):
    """
    Validate the generated Mermaid source for structural correctness.

    Checks for common Mermaid syntax errors without requiring a full
    parser — catches the most frequent LLM mistakes like missing
    diagram type declarations, unclosed brackets, and invalid node IDs.
    """

    async def run(self, ctx: GraphRunContext[DiagramState]) -> Generate | Finalise:
        """Validate draft — refine if errors found, finalise if clean."""
        assert ctx.state.inferred_type is not None
        errors = _validate_mermaid(ctx.state.draft, ctx.state.inferred_type)

        if not errors or ctx.state.iterations >= _MAX_REFINE_ITERATIONS:
            if errors:
                ctx.state.warnings.extend(
                    [f"Unresolved after {_MAX_REFINE_ITERATIONS} iterations: {e}" for e in errors]
                )
            return Finalise()

        ctx.state.validation_errors = errors
        logger.debug("Validation errors on iteration %d: %s", ctx.state.iterations, errors)
        return Generate()


@dataclass
class Finalise(BaseNode[DiagramState, None, DiagramOutput]):
    """
    Package the validated draft into the final DiagramOutput.

    Extracts a title from the diagram source if possible, otherwise
    derives one from the request description.
    """

    async def run(self, ctx: GraphRunContext[DiagramState]) -> End[DiagramOutput]:
        """Build final output and terminate the graph."""
        title = _extract_title(ctx.state.draft) or _derive_title(ctx.state.request.description)
        desc = await _generate_description(ctx.state.draft, ctx.state.request.description)

        assert ctx.state.inferred_type is not None

        output = DiagramOutput(
            mermaid_source=_clean_mermaid(ctx.state.draft),
            diagram_type=ctx.state.inferred_type,
            title=title,
            description=desc,
            iterations=ctx.state.iterations,
            warnings=ctx.state.warnings,
        )
        ctx.state.final = output
        return End(output)


################
#   GRAPH DEFINITION
################

diagram_graph = Graph[DiagramState, None, DiagramOutput](
    nodes=[Classify, GatherContext, Generate, Validate, Finalise],
)


################
#   PUBLIC API
################


async def run_diagram_agent(request: DiagramRequest) -> DiagramOutput:
    """
    Run the diagram generation graph for a given request.

    Entry point for the MCP tool wrapper. Returns a DiagramOutput
    with valid Mermaid source and metadata.
    """
    state = DiagramState(request=request)
    result = await diagram_graph.run(Classify(), state=state)
    return result.output


################
#   LLM HELPERS
################

_classifier_agent: Agent[None, DiagramType] = Agent(
    AGENT_MODEL,
    name="diagram-classifier",
    output_type=DiagramType,
    system_prompt=(
        "You are a diagram type classifier. Given a description of what needs to be diagrammed, "
        "return the single most appropriate Mermaid diagram type. "
        "Use 'flowchart' for processes and logic flows. "
        "Use 'sequence' for interactions between actors over time. "
        "Use 'state' for state machines and lifecycle diagrams. "
        "Use 'er' for data models and entity relationships. "
        "Use 'c4_context' for high-level system context diagrams. "
        "Use 'c4_component' for component-level architecture. "
        "Use 'class' for object models and type hierarchies. "
        "Use 'architecture' for infrastructure and deployment diagrams."
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)

_generator_agent: Agent[None, str] = Agent(
    AGENT_MODEL,
    name="diagram-generator",
    output_type=str,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)

_describer_agent: Agent[None, str] = Agent(
    AGENT_MODEL,
    name="diagram-describer",
    output_type=str,
    system_prompt=(
        "Write a single sentence describing what a Mermaid diagram shows. "
        "Be specific about the system or flow depicted. No preamble."
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


async def _infer_diagram_type(description: str) -> DiagramType:
    """
    Use the classifier agent to infer the best diagram type.

    Falls back to FLOWCHART if classification fails, as it is the
    most general-purpose Mermaid diagram type.
    """
    try:
        result = await _classifier_agent.run(description)
        return result.output
    except Exception as exc:
        logger.warning("Diagram type classification failed: %s — defaulting to flowchart", exc)
        return DiagramType.FLOWCHART


async def _generate_diagram(
    context: str,
    diagram_type: DiagramType,
    previous_errors: list[str],
) -> str:
    """
    Generate raw Mermaid source from context and type guidance.

    Includes previous validation errors in the prompt so the agent
    can correct them on refinement iterations.
    """
    error_block = (
        "\n\nPrevious attempt had these errors — fix them:\n" + "\n".join(f"- {e}" for e in previous_errors)
        if previous_errors
        else ""
    )

    prompt = (
        f"Generate a Mermaid {diagram_type.value} diagram for the following.\n\n"
        f"{context}"
        f"{error_block}\n\n"
        "Return ONLY the raw Mermaid source code. "
        "No markdown code fences, no explanation, no preamble. "
        "Start directly with the diagram type declaration."
    )

    result = await _generator_agent.run(prompt)
    return result.output.strip()


async def _generate_description(draft: str, original_request: str) -> str:
    """Generate a one-sentence description of the completed diagram."""
    try:
        result = await _describer_agent.run(
            f"Original request: {original_request}\n\nDiagram:\n{draft[:2000]}"
        )
        return result.output.strip()
    except Exception:
        return f"Mermaid diagram for: {original_request[:100]}"


################
#   VALIDATION
################

_DIAGRAM_HEADERS: dict[DiagramType, list[str]] = {
    DiagramType.FLOWCHART: ["flowchart", "graph"],
    DiagramType.SEQUENCE: ["sequenceDiagram"],
    DiagramType.STATE: ["stateDiagram", "stateDiagram-v2"],
    DiagramType.ER: ["erDiagram"],
    DiagramType.C4_CONTEXT: ["C4Context"],
    DiagramType.C4_COMPONENT: ["C4Component"],
    DiagramType.CLASS: ["classDiagram"],
    DiagramType.ARCHITECTURE: ["architecture-beta", "flowchart", "graph"],
}


def _validate_mermaid(source: str, diagram_type: DiagramType) -> list[str]:
    """
    Check Mermaid source for common structural errors.

    Catches the most frequent LLM generation mistakes without
    requiring a full Mermaid parser.
    """
    errors: list[str] = []
    lines = source.strip().splitlines()

    if not lines:
        errors.append("Empty diagram source.")
        return errors

    valid_headers = _DIAGRAM_HEADERS.get(diagram_type, [])
    first_line = lines[0].strip()
    if not any(first_line.startswith(h) for h in valid_headers):
        errors.append(
            f"First line '{first_line}' does not match expected headers for {diagram_type.value}: {valid_headers}"
        )

    open_brackets = source.count("{") - source.count("}")
    open_parens = source.count("(") - source.count(")")
    if open_brackets != 0:
        errors.append(f"Unbalanced curly brackets: {open_brackets:+d}")
    if open_parens != 0:
        errors.append(f"Unbalanced parentheses: {open_parens:+d}")

    if "```" in source:
        errors.append("Source contains markdown code fences — strip them.")

    return errors


################
#   UTILITIES
################


def _type_specific_guidance(diagram_type: DiagramType) -> str:
    """
    Return type-specific generation guidance for the prompt.

    Provides concrete syntax reminders for each diagram type to
    reduce the frequency of LLM syntax errors.
    """
    guidance: dict[DiagramType, str] = {
        DiagramType.FLOWCHART: (
            "Start with 'flowchart TD' or 'flowchart LR'. "
            "Node IDs must be alphanumeric with no spaces. "
            "Use --> for arrows, -- text --> for labelled arrows."
        ),
        DiagramType.SEQUENCE: (
            "Start with 'sequenceDiagram'. "
            "Use participant declarations before interactions. "
            "Use ->>, ->>, -->> for sync, async, and return messages."
        ),
        DiagramType.STATE: (
            "Start with 'stateDiagram-v2'. "
            "Use [*] for start and end states. "
            "Use --> for transitions, : for transition labels."
        ),
        DiagramType.ER: (
            "Start with 'erDiagram'. "
            "Use ||--o{ for one-to-many, }|..|{ for many-to-many. "
            "Entity names must be single words."
        ),
        DiagramType.C4_CONTEXT: (
            "Start with 'C4Context'. "
            "Use Person(), System(), System_Ext(), Rel() elements. "
            "Include a title with UpdateLayoutConfig or title directive."
        ),
        DiagramType.C4_COMPONENT: (
            "Start with 'C4Component'. "
            "Use Container(), Component(), ComponentDb(), Rel() elements."
        ),
        DiagramType.CLASS: (
            "Start with 'classDiagram'. "
            "Use <|-- for inheritance, *-- for composition, o-- for aggregation. "
            "Define methods with parentheses: +methodName() ReturnType."
        ),
        DiagramType.ARCHITECTURE: (
            "Use 'flowchart TD' or 'flowchart LR' for architecture diagrams. "
            "Group related components with subgraph blocks. "
            "Label all connections clearly."
        ),
    }
    return guidance.get(diagram_type, "Follow standard Mermaid syntax for this diagram type.")


def _clean_mermaid(source: str) -> str:
    """
    Strip markdown fences and leading/trailing whitespace from source.

    LLMs frequently wrap output in triple backticks despite instructions
    not to — this removes them defensively.
    """
    cleaned = re.sub(r"^```[a-z]*\n?", "", source.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


def _extract_title(source: str) -> str | None:
    """
    Extract a title from the Mermaid source if one is declared.

    Looks for '---\\ntitle: ...' frontmatter or a '%%title' comment.
    Returns None if no title is found.
    """
    title_match = re.search(r"title:\s*(.+)", source)
    if title_match:
        return title_match.group(1).strip()

    comment_match = re.search(r"%%\s*title:\s*(.+)", source, re.IGNORECASE)
    if comment_match:
        return comment_match.group(1).strip()

    return None


def _derive_title(description: str) -> str:
    """
    Derive a short title from the request description.

    Takes the first sentence or first 60 characters, whichever is shorter.
    """
    first_sentence = description.split(".")[0].strip()
    if len(first_sentence) <= 60:
        return first_sentence
    return description[:57].strip() + "..."