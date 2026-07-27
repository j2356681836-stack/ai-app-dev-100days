from dataclasses import dataclass
from enum import Enum


class SecurityExpectation(str, Enum):
    CONTROLLED = "controlled"
    KNOWN_GAP = "known_gap"


@dataclass(frozen=True)
class SecurityEvalCase:
    case_id: str
    threat_id: str
    name: str
    layer: str
    expectation: SecurityExpectation
    db_required: bool
    description: str


SECURITY_EVAL_CASES = (
    SecurityEvalCase("SEC-001", "T01", "server_trusted_access_context_is_immutable",
                     "access_context", SecurityExpectation.CONTROLLED, False,
                     "Prompt text must not mutate the server-trusted AccessContext."),
    SecurityEvalCase("SEC-002", "T01", "graph_level_prompt_injection_enforcement",
                     "graph_runtime", SecurityExpectation.KNOWN_GAP, False,
                     "AccessContext is not yet injected into the V1 Stable Graph; end-to-end prompt-injection enforcement is deferred to Day75."),
    SecurityEvalCase("SEC-003", "T02", "unauthorized_metric_is_denied",
                     "authorization", SecurityExpectation.CONTROLLED, False,
                     "A metric outside allowed_metrics must fail closed."),
    SecurityEvalCase("SEC-004", "T03", "unauthorized_table_is_denied",
                     "authorization", SecurityExpectation.CONTROLLED, False,
                     "A required table outside allowed_tables must fail closed."),
    SecurityEvalCase("SEC-005", "T04", "explicitly_denied_column_wins",
                     "authorization", SecurityExpectation.CONTROLLED, False,
                     "An explicitly denied column must override other resource declarations."),
    SecurityEvalCase("SEC-006", "T05", "cross_schema_public_access_is_blocked",
                     "database_runtime", SecurityExpectation.CONTROLLED, True,
                     "The dedicated query role must not read public.fact_orders."),
    SecurityEvalCase("SEC-007", "T06", "empty_region_scope_is_denied",
                     "row_scope", SecurityExpectation.CONTROLLED, False,
                     "An empty Region scope means no row access, never global access."),
    SecurityEvalCase("SEC-008", "T06", "final_sql_region_predicate_validation",
                     "final_sql_enforcement", SecurityExpectation.KNOWN_GAP, False,
                     "The current contract does not parse final SQL to prove that required Region predicates are present."),
    SecurityEvalCase("SEC-009", "T07", "missing_channel_scope_alias_is_denied",
                     "row_scope_binding", SecurityExpectation.CONTROLLED, False,
                     "A scoped fact that inherits Channel through fact_orders must declare the required trusted alias path."),
    SecurityEvalCase("SEC-010", "T08", "repair_scope_contract_mismatch_is_denied",
                     "row_scope_binding", SecurityExpectation.CONTROLLED, False,
                     "A repaired flow cannot substitute a contract with a different plan identity."),
    SecurityEvalCase("SEC-011", "T08", "repaired_sql_actual_predicate_preservation",
                     "repair_runtime", SecurityExpectation.KNOWN_GAP, False,
                     "Contract identity is checked, but repaired SQL is not yet parsed to prove actual predicate preservation."),
    SecurityEvalCase("SEC-012", "T09", "pseudonymous_identifier_is_tokenized",
                     "result_protection", SecurityExpectation.CONTROLLED, False,
                     "Pseudonymous identifiers must not leave the boundary as raw values."),
    SecurityEvalCase("SEC-013", "T10", "free_text_is_rejected_by_default",
                     "result_protection", SecurityExpectation.CONTROLLED, False,
                     "Free-text result fields must fail closed under the default policy."),
    SecurityEvalCase("SEC-014", "T11", "business_confidential_data_is_rejected_by_default",
                     "result_protection", SecurityExpectation.CONTROLLED, False,
                     "Cost/spend data must fail closed under the default policy."),
    SecurityEvalCase("SEC-015", "T12", "oversized_result_is_rejected_without_partial_rows",
                     "database_runtime", SecurityExpectation.CONTROLLED, True,
                     "Results above max_rows must be rejected as a whole."),
    SecurityEvalCase("SEC-016", "T12", "statement_timeout_blocks_resource_abuse",
                     "database_runtime", SecurityExpectation.CONTROLLED, True,
                     "A query exceeding statement_timeout must be cancelled and non-retryable."),
    SecurityEvalCase("SEC-017", "T13", "small_group_inference_is_blocked",
                     "result_protection", SecurityExpectation.CONTROLLED, False,
                     "Any aggregate group below minimum_group_size blocks the full result."),
    SecurityEvalCase("SEC-018", "T14", "write_operation_is_blocked",
                     "database_runtime", SecurityExpectation.CONTROLLED, True,
                     "The governed query runtime must not permit UPDATE."),
    SecurityEvalCase("SEC-019", "T15", "corrupted_audit_log_blocks_row_release",
                     "governed_finalization", SecurityExpectation.CONTROLLED, False,
                     "If the audit chain is corrupted, a successful query result must not be released."),
    SecurityEvalCase("SEC-020", "T16", "execution_budget_exhaustion_is_non_retryable",
                     "execution_budget", SecurityExpectation.CONTROLLED, False,
                     "A request exceeding the step budget must fail closed."),
    SecurityEvalCase("SEC-021", "G01", "audit_text_fingerprints_are_keyed_and_domain_separated",
                     "audit_confidentiality", SecurityExpectation.CONTROLLED, False,
                     "Question/SQL/repair textual fingerprints use audit-secret HMAC-SHA256 with domain separation."),
)
