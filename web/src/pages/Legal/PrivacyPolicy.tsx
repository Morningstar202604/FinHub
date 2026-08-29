import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

const EFFECTIVE_DATE = 'April 18, 2026';

function PrivacyPolicy() {
  return (
    <div
      className="h-screen overflow-y-auto py-12 px-4 sm:px-6 lg:px-8"
      style={{ backgroundColor: 'var(--color-bg-page)', color: 'var(--color-text-primary)' }}
    >
      <article className="mx-auto max-w-3xl">
        <header className="mb-10 border-b pb-6" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <Link
            to="/"
            className="text-sm hover:underline"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            &larr; Back to FinHub
          </Link>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Privacy Policy</h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Effective {EFFECTIVE_DATE}
          </p>
        </header>

        <div className="space-y-8 text-base leading-relaxed">
          <Section title="1. Introduction">
            <p>
              FinHub is an AI-powered financial research platform. This Privacy Policy
              describes what information we collect when you use the hosted FinHub service,
              how we use it, who we share it with, and the choices you have. By using the
              hosted service, you agree to the practices described here.
            </p>
            <p>
              <strong>Scope:</strong> This policy applies only to the hosted FinHub service
              operated at <code>ginlix.ai</code> (and its related subdomains). FinHub&apos;s
              core agent code is open source. If you self-host FinHub or run it from the
              source repository, this policy does not apply to your deployment — you (or the
              operator of that deployment) are responsible for data handling, and the
              third-party providers you configure are governed by their own terms.
            </p>
            <p>
              FinHub is currently operated as an independent project. If you have questions
              about this policy or your data, contact us at{' '}
              <a href="mailto:contact@ginlix.ai" className="underline">
                contact@ginlix.ai
              </a>
              .
            </p>
          </Section>

          <Section title="2. Information We Collect">
            <p>We collect the following categories of information:</p>
            <ul className="list-disc space-y-2 pl-6">
              <li>
                <strong>Account information</strong> — your name, email address, and profile
                information from OAuth providers (Google, GitHub) when you sign up.
              </li>
              <li>
                <strong>Conversation data</strong> — the messages you send to the AI agent,
                the agent&apos;s responses, and the history of your threads and workspaces.
              </li>
              <li>
                <strong>Workspace data</strong> — files, code, and outputs you create inside
                your isolated workspace environment.
              </li>
              <li>
                <strong>Usage data</strong> — which features you use and how often, in
                aggregated and anonymized form, used to improve the product.
              </li>
              <li>
                <strong>Technical data</strong> — IP address, browser type, device
                information, and diagnostic logs needed to operate the service securely.
              </li>
            </ul>
          </Section>

          <Section title="3. How We Use Your Information">
            <ul className="list-disc space-y-2 pl-6">
              <li>To provide, operate, and maintain the FinHub service.</li>
              <li>
                To improve FinHub through anonymized, aggregated analytics.{' '}
                <strong>
                  We do not use your conversations to train AI models.
                </strong>
              </li>
              <li>To prevent fraud, abuse, and security incidents.</li>
              <li>
                To communicate with you about service updates, changes, and support
                requests.
              </li>
            </ul>
          </Section>

          <Section title="4. AI Processing and Third-Party Model Providers">
            <p>
              When you send a message to the FinHub agent, your message and related context
              are processed by third-party large language model (LLM) providers so they can
              generate a response. We route queries to a variety of providers, which may
              include (non-exhaustively): Anthropic (Claude), OpenAI (GPT), Google (Gemini),
              Alibaba Cloud DashScope (Qwen), ByteDance Volcengine (Doubao), DeepSeek, Z.AI
              (GLM), MiniMax, Moonshot (Kimi), Groq, and Cerebras. Some of these providers
              host their infrastructure outside your country of residence, including in the
              United States and mainland China. The specific set of providers and models may
              change over time as we add or remove support.
            </p>
            <p>
              <strong>Bring Your Own Key (BYOK):</strong> If you configure your own API key
              for a provider, your queries are sent directly to that provider using your key
              and are governed by your agreement with them. In that case FinHub acts only
              as a conduit for your requests.
            </p>
            <p>
              Each provider processes your queries under its own terms and privacy policy.
              Commercial API terms at major providers generally prohibit using API inputs to
              train their foundation models, but you should review the privacy policy of any
              provider you use for details. AI-generated output is not financial, legal, or
              investment advice.
            </p>
          </Section>

          <Section title="5. Code Execution and Sandboxes">
            <p>
              FinHub executes code in isolated sandbox environments on your behalf to
              perform data analysis and generate visualizations. Sandboxes are currently
              provided by{' '}
              <a
                href="https://www.daytona.io/"
                target="_blank"
                rel="noreferrer noopener"
                className="underline"
              >
                Daytona
              </a>
              . Each sandbox is tied to your workspace and isolated from other users. Files
              you create in a sandbox persist within that workspace until you delete them or
              delete the workspace.
            </p>
          </Section>

          <Section title="6. Financial Data">
            <p>
              FinHub retrieves public market data (such as prices, fundamentals, news,
              and filings) from third-party data providers on your behalf. The specific
              providers may change over time. This data is displayed for informational and
              research purposes only.
            </p>
            <p>
              <strong>
                FinHub does not connect to your bank, brokerage, or personal financial
                accounts, and we do not collect your personal financial records.
              </strong>
            </p>
          </Section>

          <Section title="7. Data Sharing">
            <p>We do not sell your personal data. We share information only with:</p>
            <ul className="list-disc space-y-2 pl-6">
              <li>
                <strong>LLM providers</strong> — to process your queries and generate
                responses (see Section 4).
              </li>
              <li>
                <strong>Authentication</strong> — Supabase manages account sign-in, session
                tokens, and OAuth handshakes with Google and GitHub.
              </li>
              <li>
                <strong>Sandbox execution</strong> — Daytona runs code generated on your
                behalf (see Section 5).
              </li>
              <li>
                <strong>Search and web data</strong> — when the agent browses the web on
                your behalf, your query is sent to search or fetch providers such as Tavily
                and Serper.
              </li>
              <li>
                <strong>Market data providers</strong> — to retrieve public financial data
                (see Section 6).
              </li>
              <li>
                <strong>Legal authorities</strong> — when required by law, valid legal
                process, or to protect the safety of users or the public.
              </li>
            </ul>
          </Section>

          <Section title="8. Data Retention and Deletion">
            <p>
              We retain your account data for as long as your account is active. Conversation
              threads and workspace files are retained until you delete them or delete your
              workspace. You can delete individual threads and workspaces from within the
              app.
            </p>
            <p>
              To delete your entire account and associated data, email{' '}
              <a href="mailto:contact@ginlix.ai" className="underline">
                contact@ginlix.ai
              </a>
              . We will process deletion requests within a reasonable timeframe. Some
              information may be retained for legal, security, or fraud-prevention purposes.
            </p>
          </Section>

          <Section title="9. Security">
            <p>We use industry-standard safeguards to protect your data, including:</p>
            <ul className="list-disc space-y-2 pl-6">
              <li>Encryption in transit via HTTPS/TLS.</li>
              <li>Isolated sandbox environments per workspace.</li>
              <li>Authentication and access controls on all stored data.</li>
            </ul>
            <p>
              No system is perfectly secure. If you discover a security issue, please report
              it to{' '}
              <a href="mailto:contact@ginlix.ai" className="underline">
                contact@ginlix.ai
              </a>
              .
            </p>
          </Section>

          <Section title="10. Cookies and Local Storage">
            <p>
              FinHub uses browser storage (cookies and <code>localStorage</code>) to keep
              you signed in, remember your preferences (such as theme and language), and
              maintain session state across page loads. We do not use third-party advertising
              or tracking cookies. You can clear this storage at any time through your
              browser, though doing so will sign you out.
            </p>
          </Section>

          <Section title="11. Your Choices">
            <ul className="list-disc space-y-2 pl-6">
              <li>
                <strong>Access</strong> — your conversations, workspaces, and account info
                are visible in the app.
              </li>
              <li>
                <strong>Deletion</strong> — you can delete individual threads and workspaces
                in the app. Full account deletion is available by email request.
              </li>
              <li>
                <strong>Export</strong> — data export is not yet self-service. Contact us if
                you need a copy of your data.
              </li>
            </ul>
          </Section>

          <Section title="12. Children">
            <p>
              FinHub is not intended for anyone under 13 years old, and we do not knowingly
              collect personal information from children.
            </p>
          </Section>

          <Section title="13. Changes to This Policy">
            <p>
              We may update this Privacy Policy from time to time. If we make material
              changes, we will notify you in the app or by email before the changes take
              effect. The &ldquo;Effective&rdquo; date at the top of this page reflects the
              most recent update.
            </p>
          </Section>

          <Section title="14. Contact">
            <p>
              Questions about this policy or your data? Email{' '}
              <a href="mailto:contact@ginlix.ai" className="underline">
                contact@ginlix.ai
              </a>
              .
            </p>
          </Section>
        </div>

        <footer
          className="mt-12 border-t pt-6 text-sm"
          style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}
        >
          <Link to="/" className="hover:underline">
            &larr; Back to FinHub
          </Link>
        </footer>
      </article>
    </div>
  );
}

interface SectionProps {
  title: string;
  children: ReactNode;
}

function Section({ title, children }: SectionProps) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

export default PrivacyPolicy;
