-- Database schema for hub-api
-- SQLite database for Meltano Hub plugin data

CREATE TABLE IF NOT EXISTS plugins (
    id TEXT NOT NULL PRIMARY KEY,
    default_variant_id TEXT NOT NULL,
    plugin_type TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plugin_variants (
    id TEXT NOT NULL PRIMARY KEY,
    plugin_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    docs TEXT,
    logo_url TEXT,
    pip_url TEXT,
    executable TEXT,
    repo TEXT,
    ext_repo TEXT,
    namespace TEXT NOT NULL,
    label TEXT,
    hidden BOOLEAN,
    maintenance_status TEXT,
    quality TEXT,
    domain_url TEXT,
    definition TEXT,
    next_steps TEXT,
    settings_preamble TEXT,
    usage TEXT,
    prereq TEXT,
    supported_python_versions TEXT,
    FOREIGN KEY(plugin_id) REFERENCES plugins (id)
);

CREATE INDEX IF NOT EXISTS ix_plugin_variants_plugin_id ON plugin_variants (plugin_id);

CREATE TABLE IF NOT EXISTS settings (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    label TEXT,
    description TEXT,
    documentation TEXT,
    placeholder TEXT,
    env TEXT,
    kind TEXT,
    value TEXT,
    options TEXT,
    sensitive BOOLEAN,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_settings_variant_id ON settings (variant_id);

CREATE TABLE IF NOT EXISTS setting_aliases (
    id TEXT NOT NULL PRIMARY KEY,
    setting_id TEXT NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(setting_id) REFERENCES settings (id)
);

CREATE INDEX IF NOT EXISTS ix_setting_aliases_setting_id ON setting_aliases (setting_id);

CREATE TABLE IF NOT EXISTS setting_groups (
    variant_id TEXT NOT NULL,
    setting_id TEXT NOT NULL,
    group_id INTEGER NOT NULL,
    setting_name TEXT NOT NULL,
    PRIMARY KEY (variant_id, group_id, setting_name),
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id),
    FOREIGN KEY(setting_id) REFERENCES settings (id)
);

CREATE INDEX IF NOT EXISTS ix_setting_groups_variant_id ON setting_groups (variant_id);
CREATE INDEX IF NOT EXISTS ix_setting_groups_setting_id ON setting_groups (setting_id);

CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_capabilities_variant_id ON capabilities (variant_id);

CREATE TABLE IF NOT EXISTS keywords (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_keywords_variant_id ON keywords (variant_id);

CREATE TABLE IF NOT EXISTS commands (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    args TEXT NOT NULL,
    description TEXT,
    executable TEXT,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_commands_variant_id ON commands (variant_id);

CREATE TABLE IF NOT EXISTS plugin_requires (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    variant TEXT NOT NULL,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_plugin_requires_variant_id ON plugin_requires (variant_id);

CREATE TABLE IF NOT EXISTS selects (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    expression TEXT NOT NULL,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_selects_variant_id ON selects (variant_id);

CREATE TABLE IF NOT EXISTS metadata (
    id TEXT NOT NULL PRIMARY KEY,
    variant_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY(variant_id) REFERENCES plugin_variants (id)
);

CREATE INDEX IF NOT EXISTS ix_metadata_variant_id ON metadata (variant_id);

CREATE TABLE IF NOT EXISTS maintainers (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT,
    label TEXT,
    url TEXT
);
