"""
PDS-Ultimate Core Module
Database, LLM Engine, Scheduler, Configuration
"""

# Part 9
from pds_ultimate.core.analytics_dashboard import (
    AnalyticsDashboard,
    analytics_dashboard,
)
from pds_ultimate.core.autonomy_engine import AutonomyEngine, autonomy_engine
from pds_ultimate.core.browser_pro import BrowserProEngine, browser_pro
from pds_ultimate.core.crm_engine import CRMEngine, crm_engine
from pds_ultimate.core.database import Base, init_database
from pds_ultimate.core.evening_digest import EveningDigestEngine, evening_digest
from pds_ultimate.core.llm_engine import LLMEngine, llm_engine
from pds_ultimate.core.memory_v2 import MemoryV2Engine, memory_v2

# Part 8
from pds_ultimate.core.plugin_system import PluginManager, plugin_manager
from pds_ultimate.core.reasoning_v2 import ReasoningLayerV2, reasoning_v2
from pds_ultimate.core.scheduler import TaskScheduler, scheduler
from pds_ultimate.core.smart_triggers import TriggerManager, trigger_manager
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
]
