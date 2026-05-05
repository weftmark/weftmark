"""Schema baseline — squash of migrations 0001-0003 (through activities→projects rename).

Revision ID: b3c4d5e6f7a8
Revises:
Create Date: 2026-05-04

Squashes the full migration history up to and including the activities→projects rename
(issues #296, #311, #312). Previous head was a1b2c3d4e5f6.

Existing databases that already ran the prior chain are stamped to this revision
by entrypoint.sh before running `alembic upgrade head`.

Includes:
- alembic_meta tracking table (from 0002)
- EULA seed data: v0.3, v0.5, v0.9 (from prior baseline)
"""

# ruff: noqa: E501
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

_EULA_V03 = """\
<p style="color:#888;font-style:italic;margin-bottom:1rem">Version 0.3</p>

<div style="background:#f5f5f5;border-radius:6px;padding:1rem;margin-bottom:1.5rem">
  <p style="font-weight:600;margin-bottom:0.5rem">Plain-language summary</p>
  <ul style="padding-left:1.25rem;list-style:disc">
    <li>WeftMark is a hobby project built by a tech enthusiast for the fiber arts community — not a commercial product.</li>
    <li>By uploading content you grant WeftMark a permanent, irrevocable license to that content for platform and development purposes, including AI/ML improvements.</li>
    <li>Your content, settings, and tags may be used for AI model training and feature development unless you opt out.</li>
    <li>Data use is <strong>on by default</strong>. You can opt out at any time from Settings → Privacy &amp; data.</li>
    <li>We do not sell your data. Ever.</li>
    <li>You can delete your account and all your data at any time from your settings page.</li>
    <li>This is a hobby platform. We cannot promise 100% uptime or that it will run forever.</li>
  </ul>
</div>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">1. Who runs WeftMark</h3>
  <p>WeftMark is operated by Derek Rowland, a tech hobbyist whose family is deeply into fiber arts. It is a personal project built for the weaving and fiber arts community, not a registered company or commercial service. Contact: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">2. Accepting these terms</h3>
  <p>You must accept these Terms of Service to create an account and use WeftMark. By clicking "I Accept," you agree to these terms.</p>
  <p>If you do not accept, you may choose to delete your account from the same screen. Deleting your account permanently removes all your data from our servers.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">3. What WeftMark is</h3>
  <p>WeftMark is a web application for weavers that lets you upload and view WIF weaving draft files, track weaving projects pick by pick, manage your loom inventory and equipment, record yarn and material inventory, and upload photos of your work in progress.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">4. Your account</h3>
  <p>You sign in using a third-party identity provider (currently Google). We do not store your password — authentication is handled entirely by the provider you choose. You are responsible for the security of your account.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">5. Content license</h3>
  <p>You retain ownership of the content you upload to WeftMark, including WIF files, designs, photos, and project records.</p>
  <p>By uploading content to WeftMark, you grant WeftMark a <strong>worldwide, royalty-free, perpetual, irrevocable, non-exclusive license</strong> to store, process, display, reproduce, and use that content for any purpose related to operating, improving, or developing the platform, including but not limited to AI and machine learning model training, feature development, and quality assurance.</p>
  <p>This license survives account deletion. We will not sell your raw content to third parties.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">6. What data we collect</h3>
  <p>When you use WeftMark, we collect your email address and display name (from your identity provider), the content you create and upload, settings and tags you assign to your content, and basic usage information such as when you last used the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">7. How we use your data</h3>
  <p>We use your data to provide the WeftMark service, keep your account secure, diagnose technical problems, improve platform features, and train AI and machine learning models (see section 8). We do not sell your data to anyone, share your data with advertisers, or use your data for advertising targeting.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">8. AI and machine learning — opt-out</h3>
  <p>By default, your content, settings, and metadata — including WIF files, photos, project data, loom configurations, tags, and any other data you create on the platform — <strong>may be used for AI and machine learning model training and feature improvements</strong>.</p>
  <p>You can opt out at any time from <strong>Settings → Privacy &amp; data</strong>. Opting out stops future use of your data for AI/ML training and disables public sharing links on your account. It does not retroactively remove data already used in model training. You can opt back in at any time.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">9. Public sharing</h3>
  <p>WeftMark may offer optional public sharing links for weaving projects. Sharing is opt-in and per-project. If you have opted out of data use, public sharing links will not be accessible.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">10. Data deletion</h3>
  <p>You can permanently delete your account and all associated data at any time from your settings page. Deletion removes your content from active storage and is irreversible. Some data may remain in database backups for up to 30 days. The content license granted prior to deletion survives for content already incorporated into model training or development artifacts.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">11. Uptime and service availability</h3>
  <p>WeftMark is a hobby project. We do not promise any specific uptime or that the service will run indefinitely. We are not responsible for any loss of work or other consequences of service interruption.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">12. Acceptable use</h3>
  <p>You agree not to use WeftMark for any illegal purpose, upload content you do not own, attempt to access other users' data, use automated tools to scrape content, or use the platform to harass or harm others. We reserve the right to suspend accounts that violate these rules.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">13. Limitation of liability</h3>
  <p>WeftMark is provided "as is" without warranty of any kind. Our total liability to you for any claim is limited to zero dollars. This is a free hobby service.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">14. Changes to these terms</h3>
  <p>When we update these terms, we will update the version number and require you to accept the updated terms before continuing to use the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">15. Contact</h3>
  <p>Questions about these terms or your data: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<p style="font-size:0.75rem;color:#888;padding-top:0.5rem;border-top:1px solid #e5e5e5">
  WeftMark is an independent hobby project built for weavers. It is not affiliated with any loom manufacturer, weaving organization, or software company.
</p>
"""

_EULA_V05 = """<p style="color:#888;font-style:italic;margin-bottom:1rem">Version 0.5</p>

<div style="background:#f5f5f5;border-radius:6px;padding:1rem;margin-bottom:1.5rem">
  <p style="font-weight:600;margin-bottom:0.5rem">Plain-language summary</p>
  <ul style="padding-left:1.25rem;list-style:disc">
    <li>WeftMark is a hobby project built by a tech enthusiast for the fiber arts community — not (currently) a commercial product.</li>
    <li>By uploading content you grant WeftMark a permanent, irrevocable license to that content for platform and development purposes, including AI/ML improvements.</li>
    <li>Your content, settings, and tags may be used for AI model training and feature development unless you opt out.</li>
    <li>Data use is <strong>on by default</strong>. You can opt out at any time from Settings → Privacy &amp; data.</li>
    <li>We do not sell your data. Ever.</li>
    <li>You can delete your account and all your data at any time from your settings page.</li>
    <li>This is a hobby platform. We cannot promise 100% uptime or that it will run forever.</li>
  </ul>
</div>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">1. Who runs WeftMark</h3>
  <p>WeftMark is operated by Derek Rowland, a tech hobbyist whose family is deeply into fiber arts. It is a personal project built for the weaving and fiber arts community, not a registered company or commercial service. Contact: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">2. Accepting these terms</h3>
  <p>You must accept these Terms of Service to create an account and use WeftMark. By clicking "I Accept," you agree to these terms.</p>
  <p>If you do not accept, you may choose to delete your account from the same screen. Deleting your account permanently removes all your data from our servers.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">3. What WeftMark is</h3>
  <p>WeftMark is a web application for weavers that lets you upload and view WIF weaving draft files, track weaving projects pick by pick, manage your loom inventory and equipment, record yarn and material inventory, and upload photos of your work in progress.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">4. Your account</h3>
  <p>You sign in using a third-party identity provider (currently Google). We do not store your password — authentication is handled entirely by the provider you choose. You are responsible for the security of your account.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">5. Content license</h3>
  <p>You retain ownership of the content you upload to WeftMark, including WIF files, designs, photos, and project records.</p>
  <p>By uploading content to WeftMark, you grant WeftMark a <strong>worldwide, royalty-free, perpetual, irrevocable, non-exclusive license</strong> to store, process, display, reproduce, and use that content for any purpose related to operating, improving, or developing the platform, including but not limited to AI and machine learning model training, feature development, and quality assurance.</p>
  <p>This license survives account deletion. We will not sell your raw content to third parties.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">6. What data we collect</h3>
  <p>When you use WeftMark, we collect your email address and display name (from your identity provider), the content you create and upload, settings and tags you assign to your content, and basic usage information such as when you last used the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">7. How we use your data</h3>
  <p>We use your data to provide the WeftMark service, keep your account secure, diagnose technical problems, improve platform features, and train AI and machine learning models (see section 8). We do not sell your data to anyone, share your data with advertisers, or use your data for advertising targeting.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">8. AI and machine learning — opt-out</h3>
  <p>By default, your content, settings, and metadata — including WIF files, photos, project data, loom configurations, tags, and any other data you create on the platform — <strong>may be used for AI and machine learning model training and feature improvements</strong>.</p>
  <p>You can opt out at any time from <strong>Settings → Privacy &amp; data</strong>. Opting out stops future use of your data for AI/ML training and disables public sharing links on your account. It does not retroactively remove data already used in model training. You can opt back in at any time.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">9. Public sharing</h3>
  <p>WeftMark may offer optional public sharing links for weaving projects. Sharing is opt-in and per-project. If you have opted out of data use, public sharing links will not be accessible.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">10. Data deletion</h3>
  <p>You can permanently delete your account and all associated data at any time from your settings page. Deletion removes your content from active storage and is irreversible. Some data may remain in database backups for up to 30 days. The content license granted prior to deletion survives for content already incorporated into model training or development artifacts.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">11. Uptime and service availability</h3>
  <p>WeftMark is a hobby project. We do not promise any specific uptime or that the service will run indefinitely. We are not responsible for any loss of work or other consequences of service interruption.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">12. Acceptable use</h3>
  <p>You agree not to use WeftMark for any illegal purpose, upload content you do not own, attempt to access other users' data, use automated tools to scrape content, or use the platform to harass or harm others. We reserve the right to suspend accounts that violate these rules.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">13. Limitation of liability</h3>
  <p>WeftMark is provided "as is" without warranty of any kind. Our total liability to you for any claim is limited to zero dollars. This is a free hobby service.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">14. Changes to these terms</h3>
  <p>When we update these terms, we will update the version number and require you to accept the updated terms before continuing to use the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">15. Contact</h3>
  <p>Questions about these terms or your data: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<p style="font-size:0.75rem;color:#888;padding-top:0.5rem;border-top:1px solid #e5e5e5">
  WeftMark is an independent hobby project built for weavers. It is not affiliated with any loom manufacturer, weaving organization, or software company.
</p>
"""

_EULA_V09 = """<p style="color:#888;font-style:italic;margin-bottom:1rem">Version 0.9</p>

<div style="background:linear-gradient(135deg,#fef3c7,#fde68a);border:2px solid #d97706;border-radius:8px;padding:1.25rem;margin-bottom:1.5rem;box-shadow:0 2px 4px rgba(0,0,0,0.05)">
  <p style="font-weight:700;font-size:1.05rem;margin-bottom:0.5rem;color:#78350f">⚠️ The Megan Clause</p>
  <p style="color:#78350f;margin-bottom:0.5rem">This is the <strong>very first iteration</strong> of a pre-alpha web app. Lots of stuff will be broken. Buttons may do nothing. Pages may load sideways. The color scheme may offend.</p>
  <p style="color:#78350f;margin-bottom:0.5rem">Please:</p>
  <ul style="padding-left:1.25rem;list-style:disc;color:#78350f">
    <li>Be nice.</li>
    <li>Compliment the developer.</li>
    <li>Remember that the developer loves you and is doing his best.</li>
    <li>Save the structural feedback for after he's had coffee and at least one win.</li>
  </ul>
  <p style="color:#78350f;margin-top:0.5rem;font-style:italic">Thank you for your service. 💛</p>
</div>

<div style="background:#f5f5f5;border-radius:6px;padding:1rem;margin-bottom:1.5rem">
  <p style="font-weight:600;margin-bottom:0.5rem">Plain-language summary</p>
  <ul style="padding-left:1.25rem;list-style:disc">
    <li>WeftMark is a hobby project built by a tech enthusiast for the fiber arts community - not (currently) a commercial product.</li>
    <li>By uploading content you grant WeftMark a permanent, irrevocable license to that content for platform and development purposes, including AI/ML improvements.</li>
    <li>Your content, settings, and tags may be used for AI model training and feature development unless you opt out.</li>
    <li>Data use is <strong>on by default</strong>. You can opt out at any time from Settings → Privacy &amp; data.</li>
    <li>We do not sell your data. Ever.</li>
    <li>You can delete your account and all your data at any time from your settings page.</li>
    <li>This is a hobby platform. We cannot promise 100% uptime or that it will run forever.</li>
  </ul>
</div>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">1. Who runs WeftMark</h3>
  <p>WeftMark is operated by Derek Rowland, a tech hobbyist whose family is deeply into fiber arts. It is a personal project built for the weaving and fiber arts community, not a registered company or commercial service. Contact: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">2. Accepting these terms</h3>
  <p>You must accept these Terms of Service to create an account and use WeftMark. By clicking "I Accept," you agree to these terms.</p>
  <p>By accepting these Terms, you also acknowledge our <a href="/privacy">Privacy Policy</a>, which describes how we collect, use, and protect your personal data and explains your rights under applicable privacy laws. The Privacy Policy is incorporated into these Terms by reference.</p>
  <p>If you do not accept, you may choose to delete your account from the same screen. Deleting your account permanently removes all your data from our servers.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">3. What WeftMark is</h3>
  <p>WeftMark is a web application for weavers that lets you upload and view WIF weaving draft files, track weaving projects pick by pick, manage your loom inventory and equipment, record yarn and material inventory, and upload photos of your work in progress.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">4. Your account</h3>
  <p>You sign in using a third-party identity provider (currently Google). We do not store your password - authentication is handled entirely by the provider you choose. You are responsible for the security of your account.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">5. Content license</h3>
  <p>You retain ownership of the content you upload to WeftMark, including WIF files, designs, photos, and project records.</p>
  <p>By uploading content to WeftMark, you grant WeftMark a <strong>worldwide, royalty-free, perpetual, irrevocable, non-exclusive license</strong> to store, process, display, reproduce, and use that content for any purpose related to operating, improving, or developing the platform, including but not limited to AI and machine learning model training, feature development, and quality assurance.</p>
  <p>This license survives account deletion. We will not sell your raw content to third parties.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">6. What data we collect</h3>
  <p>When you use WeftMark, we collect your email address and display name (from your identity provider), the content you create and upload, settings and tags you assign to your content, and basic usage information such as when you last used the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">7. How we use your data</h3>
  <p>We use your data to provide the WeftMark service, keep your account secure, diagnose technical problems, improve platform features, and train AI and machine learning models (see section 8). We do not sell your data to anyone, share your data with advertisers, or use your data for advertising targeting.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">8. AI and machine learning - opt-out</h3>
  <p>By default, your content, settings, and metadata - including WIF files, photos, project data, loom configurations, tags, and any other data you create on the platform - <strong>may be used for AI and machine learning model training and feature improvements</strong>.</p>
  <p>You can opt out at any time from <strong>Settings → Privacy &amp; data</strong>. Opting out stops future use of your data for AI/ML training and disables public sharing links on your account. It does not retroactively remove data already used in model training. You can opt back in at any time.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">9. Public sharing</h3>
  <p>WeftMark may offer optional public sharing links for weaving projects. Sharing is opt-in and per-project. If you have opted out of data use, public sharing links will not be accessible.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">10. Data deletion</h3>
  <p>You can permanently delete your account and all associated data at any time from your settings page. Deletion removes your content from active storage and is irreversible. Some data may remain in database backups for up to 30 days. The content license granted prior to deletion survives for content already incorporated into model training or development artifacts.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">11. Uptime and service availability</h3>
  <p>WeftMark is a hobby project. We do not promise any specific uptime or that the service will run indefinitely. We are not responsible for any loss of work or other consequences of service interruption.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">12. Acceptable use</h3>
  <p>You agree not to use WeftMark for any illegal purpose, upload content you do not own, attempt to access other users' data, use automated tools to scrape content, or use the platform to harass or harm others. We reserve the right to suspend accounts that violate these rules.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">13. Limitation of liability</h3>
  <p>WeftMark is provided "as is" without warranty of any kind. Our total liability to you for any claim is limited to zero dollars. This is a free hobby service.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">14. Changes to these terms</h3>
  <p>When we update these terms, we will update the version number and require you to accept the updated terms before continuing to use the platform.</p>
</section>

<section style="margin-bottom:1rem">
  <h3 style="font-weight:600;margin-bottom:0.25rem">15. Contact</h3>
  <p>Questions about these terms or your data: <a href="mailto:admin@weftmark.com">admin@weftmark.com</a></p>
</section>

<p style="font-size:0.75rem;color:#888;padding-top:0.5rem;border-top:1px solid #e5e5e5">
  WeftMark is an independent hobby project built for weavers. It is not affiliated with any loom manufacturer, weaving organization, or software company.
</p>
"""

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=True),
        sa.Column("target_email", sa.String(length=255), nullable=True),
        sa.Column("details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_email", "audit_logs", ["actor_email"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_event_type"), "audit_logs", ["event_type"], unique=False)
    op.create_table(
        "eula_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_table(
        "pending_signups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pending_signups_clerk_user_id"), "pending_signups", ["clerk_user_id"], unique=True)
    op.create_table(
        "seed_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("oidc_sub", sa.String(length=512), nullable=True),
        sa.Column("clerk_user_id", sa.String(length=64), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("theme", sa.String(length=20), nullable=False),
        sa.Column("activity_theme", sa.String(length=50), nullable=True),
        sa.Column("idle_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column("measurement_system", sa.String(length=10), nullable=False),
        sa.Column("ai_training_consent", sa.Boolean(), nullable=False),
        sa.Column("eula_accepted_version", sa.String(length=20), nullable=True),
        sa.Column("eula_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_name", sa.String(length=255), nullable=True),
        sa.Column("approved_by_email", sa.String(length=255), nullable=True),
        sa.Column("clerk_banned", sa.Boolean(), nullable=False),
        sa.Column("deletion_state", sa.String(length=20), nullable=True),
        sa.Column("deletion_initiated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clerk_errored", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_clerk_user_id"), "users", ["clerk_user_id"], unique=True)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_oidc_sub"), "users", ["oidc_sub"], unique=True)
    op.create_table(
        "invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invites_email"), "invites", ["email"], unique=False)
    op.create_index(op.f("ix_invites_token"), "invites", ["token"], unique=True)
    op.create_table(
        "looms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("loom_type", sa.String(length=30), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("photo_path", sa.String(length=500), nullable=True),
        sa.Column("supports_lift_tracking", sa.Boolean(), nullable=False),
        sa.Column("supports_treadle_tracking", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_looms_owner_id"), "looms", ["owner_id"], unique=False)
    op.create_table(
        "drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("wif_filename", sa.String(length=512), nullable=False),
        sa.Column("wif_path", sa.String(length=512), nullable=False),
        sa.Column("num_shafts", sa.Integer(), nullable=True),
        sa.Column("num_treadles", sa.Integer(), nullable=True),
        sa.Column("warp_threads", sa.Integer(), nullable=True),
        sa.Column("weft_threads", sa.Integer(), nullable=True),
        sa.Column("has_threading", sa.Boolean(), nullable=False),
        sa.Column("has_tieup", sa.Boolean(), nullable=False),
        sa.Column("has_treadling", sa.Boolean(), nullable=False),
        sa.Column("has_liftplan", sa.Boolean(), nullable=False),
        sa.Column("has_color_palette", sa.Boolean(), nullable=False),
        sa.Column("liftplan_generated", sa.Boolean(), nullable=False),
        sa.Column("lint_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lint_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("wif_source_software", sa.String(length=255), nullable=True),
        sa.Column("wif_source_version", sa.String(length=100), nullable=True),
        sa.Column("preview_path", sa.String(length=512), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("share_slug", sa.String(length=64), nullable=True),
        sa.Column("effective_num_treadles", sa.Integer(), nullable=True),
        sa.Column("effective_num_shafts", sa.Integer(), nullable=True),
        sa.Column("wif_modified_path", sa.String(length=512), nullable=True),
        sa.Column("metadata_overrides", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_slug"),
    )
    op.create_index("ix_drafts_owner_id", "drafts", ["owner_id"], unique=False)
    op.create_table(
        "user_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_sub", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_sub", name="uq_user_identities_provider_sub"),
    )
    op.create_index(op.f("ix_user_identities_user_id"), "user_identities", ["user_id"], unique=False)
    op.create_table(
        "yarns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("weight_notation", sa.String(length=20), nullable=True),
        sa.Column("weight_category", sa.String(length=30), nullable=True),
        sa.Column("fiber_content", sa.String(length=255), nullable=True),
        sa.Column("color_name", sa.String(length=255), nullable=True),
        sa.Column("color_hex", sa.String(length=7), nullable=True),
        sa.Column("unit_weight_oz", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("unit_weight_g", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("unit_yardage", sa.Numeric(precision=10, scale=1), nullable=True),
        sa.Column("yards_per_pound", sa.Numeric(precision=10, scale=1), nullable=True),
        sa.Column("sett_min", sa.Integer(), nullable=True),
        sa.Column("sett_max", sa.Integer(), nullable=True),
        sa.Column("purchase_source", sa.String(length=255), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_yarns_owner_id"), "yarns", ["owner_id"], unique=False)
    op.create_table(
        "loom_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loom_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("num_shafts", sa.Integer(), nullable=True),
        sa.Column("num_treadles", sa.Integer(), nullable=True),
        sa.Column("num_heddles", sa.Integer(), nullable=True),
        sa.Column("weaving_width", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("weaving_width_unit", sa.String(length=5), nullable=False),
        sa.Column("warp_waste_allowance", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("warp_waste_unit", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_id"], ["looms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_loom_versions_loom_id"), "loom_versions", ["loom_id"], unique=False)
    op.create_table(
        "skeins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("yarn_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_yardage", sa.Numeric(precision=10, scale=1), nullable=True),
        sa.Column("current_weight_oz", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("current_weight_g", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["yarn_id"], ["yarns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skeins_yarn_id"), "skeins", ["yarn_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("draft_id", sa.UUID(), nullable=False),
        sa.Column("loom_id", sa.UUID(), nullable=True),
        sa.Column("loom_version_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("project_type", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_pick", sa.Integer(), nullable=False),
        sa.Column("total_picks", sa.Integer(), nullable=False),
        sa.Column("finished_length_per_item", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("num_items", sa.Integer(), nullable=False),
        sa.Column("waste_between_items", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("warp_waste_allowance", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("length_unit", sa.String(length=5), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"]),
        sa.ForeignKeyConstraint(["loom_id"], ["looms.id"]),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_index("ix_projects_draft_id", "projects", ["draft_id"], unique=False)
    op.create_table(
        "loom_version_accessories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loom_version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_loom_version_accessories_loom_version_id"), "loom_version_accessories", ["loom_version_id"], unique=False)
    op.create_table(
        "loom_version_photos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loom_version_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_loom_version_photos_loom_version_id"), "loom_version_photos", ["loom_version_id"], unique=False)
    op.create_table(
        "loom_version_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loom_version_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_loom_version_receipts_loom_version_id"), "loom_version_receipts", ["loom_version_id"], unique=False)
    op.create_table(
        "project_photos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_photos_project_id"), "project_photos", ["project_id"], unique=False)
    op.create_table(
        "project_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=10), nullable=False),
        sa.Column("from_pick", sa.Integer(), nullable=False),
        sa.Column("to_pick", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_steps_project_id"), "project_steps", ["project_id"], unique=False)

    # alembic_meta tracking table (from 0002)
    op.create_table(
        "alembic_meta",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="alembic_meta_pkey"),
    )
    op.execute(
        "INSERT INTO alembic_meta (key, value) VALUES ('last_squash_at', '2026-05-04') "
        "ON CONFLICT (key) DO NOTHING"
    )

    # Seed required EULA versions — consolidated from migrations 0025, 0027, 0028
    _eula_sql = sa.text(
        "INSERT INTO eula_versions (version, body_html, effective_date) "
        "VALUES (:version, :body_html, :effective_date) "
        "ON CONFLICT (version) DO NOTHING"
    )
    op.execute(_eula_sql.bindparams(version="0.3", body_html=_EULA_V03, effective_date="2026-04-01T00:00:00+00:00"))
    op.execute(_eula_sql.bindparams(version="0.5", body_html=_EULA_V05, effective_date="2026-04-28T03:29:00Z"))
    op.execute(_eula_sql.bindparams(version="0.9", body_html=_EULA_V09, effective_date="2026-04-29T00:37:00Z"))


def downgrade() -> None:
    op.drop_index(op.f("ix_project_steps_project_id"), table_name="project_steps")
    op.drop_table("project_steps")
    op.drop_index(op.f("ix_project_photos_project_id"), table_name="project_photos")
    op.drop_table("project_photos")
    op.drop_index(op.f("ix_loom_version_receipts_loom_version_id"), table_name="loom_version_receipts")
    op.drop_table("loom_version_receipts")
    op.drop_index(op.f("ix_loom_version_photos_loom_version_id"), table_name="loom_version_photos")
    op.drop_table("loom_version_photos")
    op.drop_index(op.f("ix_loom_version_accessories_loom_version_id"), table_name="loom_version_accessories")
    op.drop_table("loom_version_accessories")
    op.drop_index("ix_projects_draft_id", table_name="projects")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_skeins_yarn_id"), table_name="skeins")
    op.drop_table("skeins")
    op.drop_index(op.f("ix_loom_versions_loom_id"), table_name="loom_versions")
    op.drop_table("loom_versions")
    op.drop_index(op.f("ix_yarns_owner_id"), table_name="yarns")
    op.drop_table("yarns")
    op.drop_index(op.f("ix_user_identities_user_id"), table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_index("ix_drafts_owner_id", table_name="drafts")
    op.drop_table("drafts")
    op.drop_index(op.f("ix_looms_owner_id"), table_name="looms")
    op.drop_table("looms")
    op.drop_index(op.f("ix_invites_token"), table_name="invites")
    op.drop_index(op.f("ix_invites_email"), table_name="invites")
    op.drop_table("invites")
    op.drop_index(op.f("ix_users_oidc_sub"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_clerk_user_id"), table_name="users")
    op.drop_table("users")
    op.execute("DROP TABLE IF EXISTS seed_runs")
    op.drop_index(op.f("ix_pending_signups_clerk_user_id"), table_name="pending_signups")
    op.drop_table("pending_signups")
    op.drop_table("eula_versions")
    op.drop_index(op.f("ix_audit_logs_event_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_email", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("alembic_meta")
