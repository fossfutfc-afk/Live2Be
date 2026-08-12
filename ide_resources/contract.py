
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

KIND_CHARACTER_WRITE_REQUEST = 'character_write_request'

CHARACTER_FILES = (
    'profile.yml',
    'personality.yml',
    'knowledge.yml',
    'experience.yml',
    'typical.yml',
)

CHARACTER_FILE_SET = frozenset(CHARACTER_FILES)
REQUIRED_FILE = 'profile.yml'
ALLOWED_MODES = frozenset(('create', 'merge', 'overwrite'))
CHARACTER_ID_PATTERN = re.compile(r'^[a-z0-9_]+$')
MAX_CHARACTER_ID_LENGTH = 64
MAX_SUMMARY_LENGTH = 1000
MAX_LIST_ITEMS = 20

class ContractError(ValueError):
    pass

@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if not self.is_valid:
            raise ContractError('\n'.join(self.errors))

def _normalize_interperson_content(raw: Any) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict):
        raise ContractError('interperson.content must be an object')
    result: dict[str, dict[str, int]] = {}
    for char_id, relations in raw.items():
        if not isinstance(char_id, str) or not char_id.strip():
            raise ContractError('interperson keys must be non-empty strings')
        if not isinstance(relations, dict):
            raise ContractError('interperson relations must be objects')
        clean_relations: dict[str, int] = {}
        for name, weight in relations.items():
            if not isinstance(name, str) or not name.strip():
                raise ContractError('relation names must be non-empty strings')
            if isinstance(weight, bool) or not isinstance(weight, int):
                raise ContractError('relation weights must be integers')
            clean_relations[name] = weight
        result[char_id] = clean_relations
    return result

@dataclass(frozen=True)
class InterpersonProposal:
    changed: bool
    content: dict[str, dict[str, int]] | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> 'InterpersonProposal':
        if not isinstance(raw, dict):
            raise ContractError('interperson must be an object')
        changed = raw.get('changed', False)
        if not isinstance(changed, bool):
            raise ContractError('interperson.changed must be boolean')
        content = raw.get('content')
        normalized = None
        if content is not None:
            normalized = _normalize_interperson_content(content)
        return cls(changed=changed, content=normalized)

    def to_dict(self) -> dict[str, Any]:
        return {'changed': self.changed, 'content': self.content}

    def validate(self) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if self.changed and self.content is None:
            errors.append('interperson.changed requires content')
        if not self.changed and self.content is not None:
            warnings.append('interperson will not be written when changed=false')
        return ValidationResult(tuple(errors), tuple(warnings))

@dataclass(frozen=True)
class CharacterWriteRequest:
    kind: str = ''
    summary: str = ''
    character_id: str = ''
    display_name: str = ''
    mode: str = 'create'
    files: dict[str, str] = field(default_factory=dict)
    interperson: InterpersonProposal = field(
        default_factory=lambda: InterpersonProposal(False)
    )
    sources: tuple[str, ...] = ()
    basis: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> 'CharacterWriteRequest':
        if not isinstance(raw, dict):
            raise ContractError('request must be an object')
        kind = raw.get('kind', '')
        summary = raw.get('summary', '')
        character_id = raw.get('character_id', '')
        display_name = raw.get('display_name', '')
        mode = raw.get('mode', 'create')
        files = _normalize_files(raw.get('files', {}))
        interperson = InterpersonProposal.from_dict(raw.get('interperson', {}))
        sources = _normalize_strings(raw.get('sources', []), 'sources')
        basis = _normalize_strings(raw.get('basis', []), 'basis')
        return cls(
            kind=kind,
            summary=summary,
            character_id=character_id,
            display_name=display_name,
            mode=mode,
            files=files,
            interperson=interperson,
            sources=sources,
            basis=basis,
        )

    def to_dict(self) -> dict[str, Any]:
        interperson = self.interperson.to_dict()
        return {
            'kind': self.kind,
            'summary': self.summary,
            'character_id': self.character_id,
            'display_name': self.display_name,
            'mode': self.mode,
            'files': dict(self.files),
            'interperson': interperson,
            'sources': list(self.sources),
            'basis': list(self.basis),
        }

    def validate(self, *, require_all_files: bool = True) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if self.kind != KIND_CHARACTER_WRITE_REQUEST:
            errors.append('kind must be character_write_request')
        if not self.summary.strip():
            errors.append('summary must not be empty')
        elif len(self.summary) > MAX_SUMMARY_LENGTH:
            errors.append('summary is too long')
        if not CHARACTER_ID_PATTERN.fullmatch(self.character_id):
            errors.append('character_id must match [a-z0-9_]+')
        elif len(self.character_id) > MAX_CHARACTER_ID_LENGTH:
            errors.append('character_id is too long')
        if not self.display_name.strip():
            errors.append('display_name must not be empty')
        if self.mode not in ALLOWED_MODES:
            errors.append('mode must be create, merge, or overwrite')
        self._validate_files(errors, warnings, require_all_files)
        ir_result = self.interperson.validate()
        errors.extend(ir_result.errors)
        warnings.extend(ir_result.warnings)
        if not self.sources:
            warnings.append('no sources provided')
        return ValidationResult(tuple(errors), tuple(warnings))

    def _validate_files(
        self,
        errors: list[str],
        _warnings: list[str],
        require_all_files: bool,
    ) -> None:
        if require_all_files:
            missing = [name for name in CHARACTER_FILES if name not in self.files]
            if missing:
                errors.append('missing files: ' + ', '.join(missing))
        elif REQUIRED_FILE not in self.files:
            errors.append('missing required file: ' + REQUIRED_FILE)
        for name, content in self.files.items():
            if name not in CHARACTER_FILE_SET:
                errors.append('unknown file name: ' + name)
                continue
            if not isinstance(content, str) or not content.strip():
                errors.append(name + ' must be non-empty')

def _normalize_files(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ContractError('files must be an object')
    result: dict[str, str] = {}
    for name, content in raw.items():
        if name not in CHARACTER_FILE_SET:
            raise ContractError('unknown file name: ' + str(name))
        if not isinstance(content, str):
            raise ContractError('file content must be a string')
        result[name] = content
    return result

def _normalize_strings(raw: Any, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ContractError(label + ' must be a list')
    if len(raw) > MAX_LIST_ITEMS:
        raise ContractError(label + ' exceeds ' + str(MAX_LIST_ITEMS) + ' items')
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ContractError(label + ' items must be non-empty strings')
        result.append(item)
    return tuple(result)

def parse_character_write_request(
    raw: Any,
    *,
    require_all_files: bool = True,
) -> tuple[CharacterWriteRequest | None, ValidationResult]:
    try:
        request = CharacterWriteRequest.from_dict(raw)
    except ContractError as exc:
        return None, ValidationResult(errors=(str(exc),))
    result = request.validate(require_all_files=require_all_files)
    return request, result
