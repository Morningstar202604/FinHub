import { useCallback, useMemo } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Plus, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ProviderCard } from "./ProviderCard"
import { ApiKeyInput, type TestResult } from "./ApiKeyInput"
import type { ByokProvider } from "./types"

export interface ProviderManagerProps {
  /** All available providers from the static manifest */
  providers: Array<{
    provider: string
    display_name: string
    byok_eligible?: boolean
  }>
  /** Currently configured providers (from API) */
  configuredProviders: ByokProvider[]
  /** The currently selected provider (for key input) */
  selectedProvider: string | null
  onSelectProvider: (provider: string | null) => void
  /** Key input values (provider -> key string) */
  keyInputs: Record<string, string>
  onKeyChange: (provider: string, value: string) => void
  /** Base URL input values */
  baseUrlInputs: Record<string, string>
  onBaseUrlChange: (provider: string, value: string) => void
  /** Provider requires base URL (check provider config) */
  providerNeedsBaseUrl?: (provider: string) => boolean
  /** Test key callback */
  onTestKey?: (provider: string, apiKey: string) => Promise<TestResult>
  /** Delete a configured provider's key */
  onDeleteProvider?: (provider: string) => void
}

/** Set of configured provider IDs for fast lookup */
function useConfiguredSet(configured: ByokProvider[]): Set<string> {
  return useMemo(() => new Set(configured.map((p) => p.provider)), [configured])
}

export function ProviderManager({
  providers,
  configuredProviders,
  selectedProvider,
  onSelectProvider,
  keyInputs,
  onKeyChange,
  baseUrlInputs,
  onBaseUrlChange,
  providerNeedsBaseUrl,
  onTestKey,
  onDeleteProvider,
}: ProviderManagerProps) {
  const configuredSet = useConfiguredSet(configuredProviders)

  // Only show byok-eligible providers (exclude explicit false)
  const eligibleProviders = useMemo(
    () => providers.filter((p) => p.byok_eligible !== false),
    [providers],
  )

  const handleSelect = useCallback(
    (provider: string) => {
      // Toggle: clicking the already-selected provider deselects it
      onSelectProvider(selectedProvider === provider ? null : provider)
    },
    [selectedProvider, onSelectProvider],
  )

  const handleAddAnother = useCallback(() => {
    onSelectProvider(null)
  }, [onSelectProvider])

  const handleDeleteChip = useCallback(
    (provider: string) => {
      onDeleteProvider?.(provider)
      // If the deleted provider was selected, deselect it
      if (selectedProvider === provider) {
        onSelectProvider(null)
      }
    },
    [onDeleteProvider, selectedProvider, onSelectProvider],
  )

  // Resolve the configured provider data for the selected provider
  const selectedConfigured = useMemo(
    () =>
      selectedProvider
        ? configuredProviders.find((p) => p.provider === selectedProvider)
        : undefined,
    [selectedProvider, configuredProviders],
  )

  const showBaseUrl =
    selectedProvider != null && providerNeedsBaseUrl?.(selectedProvider)

  return (
    <div className="flex flex-col gap-4">
      {/* Configured providers chips */}
      {configuredProviders.length > 0 && (
        <div className="flex flex-wrap gap-2" role="list" aria-label="Configured providers">
          {configuredProviders.map((cp) => (
            <span
              key={cp.provider}
              role="listitem"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full text-xs font-medium",
                "p-1.5 select-none",
              )}
              style={{
                background: "var(--color-bg-surface)",
                border: "1px solid var(--color-border-default)",
                color: "var(--color-text-primary)",
              }}
            >
              {cp.display_name}
              {onDeleteProvider && (
                <button
                  type="button"
                  onClick={() => handleDeleteChip(cp.provider)}
                  className="inline-flex items-center justify-center rounded-full p-0.5 transition-colors hover:bg-black/5 dark:hover:bg-white/10"
                  style={{ color: "var(--color-text-tertiary)" }}
                  aria-label={`Remove ${cp.display_name}`}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "var(--color-loss)"
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "var(--color-text-tertiary)"
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Provider grid */}
      <div
        role="radiogroup"
        aria-label="Choose your AI provider"
        className="grid grid-cols-2 sm:grid-cols-3 gap-3"
      >
        {eligibleProviders.map((p) => (
          <ProviderCard
            key={p.provider}
            provider={p.provider}
            displayName={p.display_name}
            selected={selectedProvider === p.provider}
            configured={configuredSet.has(p.provider)}
            onSelect={handleSelect}
          />
        ))}
      </div>

      {/* Key input form — animated expand/collapse */}
      <AnimatePresence initial={false}>
        {selectedProvider && (
          <motion.div
            key={selectedProvider}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden -mx-1"
          >
            <div className="pt-1 pb-2 px-1">
              <label
                className="block text-sm font-medium mb-2"
                style={{ color: "var(--color-text-primary)" }}
              >
                {eligibleProviders.find((p) => p.provider === selectedProvider)
                  ?.display_name ?? selectedProvider}{" "}
                API Key
              </label>
              <ApiKeyInput
                provider={selectedProvider}
                value={keyInputs[selectedProvider] ?? ""}
                onChange={(val) => onKeyChange(selectedProvider, val)}
                maskedKey={selectedConfigured?.masked_key}
                baseUrl={baseUrlInputs[selectedProvider] ?? ""}
                onBaseUrlChange={(val) =>
                  onBaseUrlChange(selectedProvider, val)
                }
                showBaseUrl={showBaseUrl}
                onTest={onTestKey}
              />

              {/* "Add another provider" link — show when key is entered or provider is already configured */}
              {(configuredSet.has(selectedProvider) || Boolean(keyInputs[selectedProvider])) && (
                <button
                  type="button"
                  onClick={handleAddAnother}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium transition-colors"
                  style={{ color: "var(--color-accent-primary)" }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add another provider
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
