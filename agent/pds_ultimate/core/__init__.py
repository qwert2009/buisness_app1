"""
PDS-Ultimate Core Module
Database, LLM Engine, Scheduler, Configuration
"""

# Part 9
# Part 10
from pds_ultimate.core.adaptive_query import AdaptiveQueryEngine, adaptive_query
from pds_ultimate.core.analytics_dashboard import (
    AnalyticsDashboard,
    analytics_dashboard,
)
from pds_ultimate.core.autonomy_engine import AutonomyEngine, autonomy_engine
from pds_ultimate.core.browser_pro import BrowserProEngine, browser_pro
from pds_ultimate.core.confidence_tracker import ConfidenceTracker, confidence_tracker
from pds_ultimate.core.context_compressor import ContextCompressorV2, context_compressor
from pds_ultimate.core.crm_engine import CRMEngine, crm_engine
from pds_ultimate.core.database import Base, init_database
from pds_ultimate.core.evening_digest import EveningDigestEngine, evening_digest

# Part 11
from pds_ultimate.core.integration_layer import IntegrationLayer, integration_layer
from pds_ultimate.core.llm_engine import LLMEngine, llm_engine

# Part 12
from pds_ultimate.core.production import ProductionHardening, production
from pds_ultimate.core.memory_v2 import MemoryV2Engine, memory_v2

# Part 8
from pds_ultimate.core.plugin_system import PluginManager, plugin_manager
from pds_ultimate.core.reasoning_v2 import ReasoningLayerV2, reasoning_v2
from pds_ultimate.core.scheduler import TaskScheduler, scheduler
from pds_ultimate.core.semantic_search_v2 import SemanticSearchV2, semantic_search_v2
from pds_ultimate.core.smart_triggers import TriggerManager, trigger_manager
from pds_ultimate.core.task_prioritizer import TaskPrioritizer, task_prioritizer
from pds_ultimate.core.time_relevance import TimeRelevanceEngine, time_relevance
from pds_ultimate.core.workflow_engine import WorkflowEngine, workflow_engine

__all__ = [
    "init_database",
    "Base",
    "llm_engine",
    "LLMEngine",
    "scheduler",
    "TaskScheduler",
    # Part 8
    "PluginManager",
    "plugin_manager",
    "AutonomyEngine",
    "autonomy_engine",
    "BrowserProEngine",
    "browser_pro",
    "ReasoningLayerV2",
    "reasoning_v2",
    "MemoryV2Engine",
    "memory_v2",
    # Part 9
    "TriggerManager",
    "trigger_manager",
    "AnalyticsDashboard",
    "analytics_dashboard",
    "CRMEngine",
    "crm_engine",
    "EveningDigestEngine",
    "evening_digest",
    "WorkflowEngine",
    "workflow_engine",
    # Part 10
    "SemanticSearchV2",
    "semantic_search_v2",
    "ConfidenceTracker",
    "confidence_tracker",
    "AdaptiveQueryEngine",
    "adaptive_query",
    "TaskPrioritizer",
    "task_prioritizer",
    "ContextCompressorV2",
    "context_compressor",
    "TimeRelevanceEngine",
    "time_relevance",
    # Part 11
    "IntegrationLayer",
    "integration_layer",
    # Part 12
    "ProductionHardening",
    "production",
]
