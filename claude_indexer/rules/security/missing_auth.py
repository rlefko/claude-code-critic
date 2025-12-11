"""
Missing authentication detection rule.

Detects routes, endpoints, and handlers that may be missing
authentication or authorization checks.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class MissingAuthRule(BaseRule):
    """Detect routes and endpoints potentially missing authentication."""

    # Language-specific patterns for missing authentication
    # Format: (pattern, description, confidence, auth_patterns)
    PATTERNS = {
        "python": [
            # Flask routes - check for auth decorators
            (
                r'@app\.route\s*\(\s*["\'][^"\']+["\']\s*(?:,\s*methods\s*=\s*\[[^\]]+\])?\s*\)',
                "Flask route",
                0.60,
                [r'@login_required', r'@auth', r'@jwt_required', r'@requires_auth', r'@permission', r'@protected'],
            ),
            # Flask blueprint routes
            (
                r'@\w+\.route\s*\(\s*["\'][^"\']+["\']\s*(?:,\s*methods\s*=\s*\[[^\]]+\])?\s*\)',
                "Flask blueprint route",
                0.60,
                [r'@login_required', r'@auth', r'@jwt_required', r'@requires_auth'],
            ),
            # Django REST Framework views
            (
                r'class\s+\w+\s*\([^)]*(?:APIView|ViewSet|ModelViewSet)',
                "Django REST view",
                0.55,
                [r'permission_classes', r'authentication_classes', r'IsAuthenticated', r'@permission'],
            ),
            # FastAPI routes
            (
                r'@(?:app|router)\.(get|post|put|patch|delete)\s*\(',
                "FastAPI endpoint",
                0.55,
                [r'Depends\s*\([^)]*(?:auth|user|token|current)', r'@requires', r'Security\s*\('],
            ),
            # Django view functions
            (
                r'def\s+\w+\s*\(\s*request\s*(?:,|\))',
                "Django view function",
                0.50,
                [r'@login_required', r'@permission_required', r'@user_passes_test'],
            ),
        ],
        "javascript": [
            # Express routes
            (
                r'(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*["\'][^"\']+["\']',
                "Express route",
                0.55,
                [r'auth', r'passport', r'jwt', r'authenticate', r'isAuthenticated', r'requireAuth', r'protect'],
            ),
            # NestJS controllers
            (
                r'@(Get|Post|Put|Patch|Delete)\s*\(\s*["\']?[^)]*\)',
                "NestJS endpoint",
                0.55,
                [r'@UseGuards', r'AuthGuard', r'@ApiBearerAuth', r'@Auth'],
            ),
            # Koa routes
            (
                r'router\.(get|post|put|patch|delete)\s*\(',
                "Koa route",
                0.55,
                [r'auth', r'jwt', r'isAuthenticated'],
            ),
            # Hapi routes
            (
                r'server\.route\s*\(\s*\{[^}]*path\s*:',
                "Hapi route",
                0.55,
                [r'auth\s*:', r'strategy\s*:'],
            ),
        ],
        "typescript": [
            # Express routes (TypeScript)
            (
                r'(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*["\'][^"\']+["\']',
                "Express route",
                0.55,
                [r'auth', r'passport', r'jwt', r'authenticate', r'isAuthenticated', r'requireAuth'],
            ),
            # NestJS controllers
            (
                r'@(Get|Post|Put|Patch|Delete)\s*\(\s*["\']?[^)]*\)',
                "NestJS endpoint",
                0.55,
                [r'@UseGuards', r'AuthGuard', r'@ApiBearerAuth', r'@Auth'],
            ),
            # tRPC procedures
            (
                r'\.(query|mutation)\s*\(',
                "tRPC procedure",
                0.50,
                [r'protectedProcedure', r'authMiddleware', r'isAuthed'],
            ),
        ],
        "java": [
            # Spring MVC controllers
            (
                r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\s*\(',
                "Spring endpoint",
                0.55,
                [r'@PreAuthorize', r'@Secured', r'@RolesAllowed', r'SecurityContext', r'@AuthenticationPrincipal'],
            ),
            # JAX-RS resources
            (
                r'@(GET|POST|PUT|DELETE)\s*\n\s*@Path',
                "JAX-RS endpoint",
                0.55,
                [r'@RolesAllowed', r'@PermitAll', r'@DenyAll', r'SecurityContext'],
            ),
        ],
        "go": [
            # HTTP handlers
            (
                r'http\.HandleFunc\s*\(\s*["\'][^"\']+["\']',
                "HTTP handler",
                0.50,
                [r'auth', r'middleware', r'jwt', r'session', r'token'],
            ),
            # Gin routes
            (
                r'(?:router|r|g)\.(GET|POST|PUT|DELETE|PATCH)\s*\(',
                "Gin route",
                0.55,
                [r'AuthMiddleware', r'JWTAuth', r'RequireAuth'],
            ),
            # Echo routes
            (
                r'e\.(GET|POST|PUT|DELETE|PATCH)\s*\(',
                "Echo route",
                0.55,
                [r'middleware\.JWT', r'AuthMiddleware', r'RequireAuth'],
            ),
        ],
        "ruby": [
            # Rails controller actions
            (
                r'def\s+(index|show|create|update|destroy|new|edit)\b',
                "Rails controller action",
                0.50,
                [r'before_action.*authenticate', r'authenticate_user', r'current_user', r'authorize', r'pundit'],
            ),
            # Sinatra routes
            (
                r'(get|post|put|patch|delete)\s+["\'][^"\']+["\']',
                "Sinatra route",
                0.55,
                [r'authenticate', r'authorized', r'protected', r'login_required'],
            ),
        ],
        "php": [
            # Laravel routes
            (
                r'Route::(get|post|put|patch|delete)\s*\(',
                "Laravel route",
                0.55,
                [r'->middleware\s*\(\s*["\']auth', r'auth:', r'can:', r'@can'],
            ),
            # Symfony controllers
            (
                r'#\[Route\s*\(',
                "Symfony endpoint",
                0.55,
                [r'#\[IsGranted', r'@Security', r'$this->denyAccessUnlessGranted'],
            ),
        ],
    }

    # Public route patterns that typically don't need auth
    PUBLIC_ROUTE_PATTERNS = [
        r'/health',
        r'/ping',
        r'/status',
        r'/ready',
        r'/live',
        r'/metrics',
        r'/public',
        r'/static',
        r'/assets',
        r'/login',
        r'/signin',
        r'/signup',
        r'/register',
        r'/logout',
        r'/forgot',
        r'/reset',
        r'/webhook',
        r'/callback',
        r'/oauth',
        r'/\.well-known',
        r'/robots\.txt',
        r'/sitemap',
        r'/favicon',
    ]

    @property
    def rule_id(self) -> str:
        return "SECURITY.MISSING_AUTH"

    @property
    def name(self) -> str:
        return "Missing Authentication Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return list(self.PATTERNS.keys())

    @property
    def description(self) -> str:
        return (
            "Detects routes, endpoints, and handlers that may be missing "
            "authentication or authorization checks."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_public_route(self, line: str) -> bool:
        """Check if the route appears to be intentionally public."""
        for pattern in self.PUBLIC_ROUTE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def _has_auth_check(self, surrounding_lines: list[str], auth_patterns: list[str]) -> bool:
        """Check if authentication is present in surrounding code."""
        text = " ".join(surrounding_lines)
        for pattern in auth_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for missing authentication.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for routes potentially missing authentication
        """
        findings = []
        language = context.language

        # Get patterns for this language
        pattern_data = self.PATTERNS.get(language, [])
        if not pattern_data:
            return findings

        file_path_str = str(context.file_path)

        # Check if this is a test file
        is_test_file = any(
            marker in file_path_str.lower()
            for marker in ["test_", "_test", "tests/", "spec/", "mock/", "fixture"]
        )

        # Skip test files entirely for this rule
        if is_test_file:
            return findings

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, route_type, base_confidence, auth_patterns in pattern_data:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip intentionally public routes
                    if self._is_public_route(line):
                        continue

                    # Get surrounding lines for auth check
                    # Look at decorators above and code below
                    start = max(0, line_num - 10)  # Look further up for decorators
                    end = min(len(lines), line_num + 5)
                    surrounding = lines[start:end]

                    # Check if authentication is present
                    if self._has_auth_check(surrounding, auth_patterns):
                        continue  # Auth is present, skip

                    findings.append(
                        self._create_finding(
                            summary=f"Potentially missing authentication: {route_type}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=f"{route_type} without apparent authentication",
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
                                        "route_type": route_type,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hints(language),
                            confidence=base_confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        hints = {
            "python": [
                "Add @login_required decorator for Flask routes",
                "Add permission_classes to Django REST views",
                "Use Depends() with auth function for FastAPI endpoints",
            ],
            "javascript": [
                "Add authentication middleware to Express routes",
                "Use @UseGuards(AuthGuard) for NestJS endpoints",
                "Implement passport.js or JWT middleware for protected routes",
            ],
            "typescript": [
                "Add authentication middleware to routes",
                "Use @UseGuards(AuthGuard) for NestJS endpoints",
                "Implement proper auth checks in tRPC procedures",
            ],
            "java": [
                "Add @PreAuthorize or @Secured annotation to Spring endpoints",
                "Use @RolesAllowed for JAX-RS resources",
                "Configure Spring Security for URL-based authorization",
            ],
            "go": [
                "Add authentication middleware to HTTP handlers",
                "Use Gin/Echo auth middleware for protected routes",
                "Implement JWT or session validation middleware",
            ],
            "ruby": [
                "Add before_action :authenticate_user! for Rails controllers",
                "Use Pundit or CanCanCan for authorization",
                "Implement protected! helper for Sinatra routes",
            ],
            "php": [
                "Add ->middleware('auth') to Laravel routes",
                "Use #[IsGranted] attribute for Symfony controllers",
                "Implement authentication gates and policies",
            ],
        }
        return hints.get(language, [
            "Add authentication middleware or decorator to this endpoint",
            "Verify this endpoint should be publicly accessible",
            "If intentionally public, add a comment explaining why",
        ])
