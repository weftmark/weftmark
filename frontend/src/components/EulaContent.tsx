export function EulaContent() {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none space-y-4 text-sm leading-relaxed">
      <p className="text-muted-foreground italic">Version 0.3</p>

      <div className="rounded-md bg-muted px-4 py-3 text-sm">
        <p className="font-medium mb-1">Plain-language summary</p>
        <ul className="space-y-1 list-disc list-inside text-muted-foreground">
          <li>WeftMark is a hobby project built by a tech enthusiast for the fiber arts community — not a commercial product.</li>
          <li>By uploading content you grant WeftMark a permanent, irrevocable license to that content for platform and development purposes, including AI/ML improvements.</li>
          <li>Your content, settings, and tags may be used for AI model training and feature development unless you opt out.</li>
          <li>Data use is <strong>on by default</strong>. You can opt out at any time from Settings → Privacy &amp; data.</li>
          <li>We do not sell your data. Ever.</li>
          <li>You can delete your account and all your data at any time from your settings page.</li>
          <li>This is a hobby platform. We cannot promise 100% uptime or that it will run forever.</li>
        </ul>
      </div>

      <section>
        <h3 className="font-semibold">1. Who runs WeftMark</h3>
        <p>WeftMark is operated by Derek Rowland, a tech hobbyist whose family is deeply into fiber arts. It is a personal project built for the weaving and fiber arts community, not a registered company or commercial service. Contact: <a href="mailto:hello@weftmark.com" className="underline">hello@weftmark.com</a></p>
      </section>

      <section>
        <h3 className="font-semibold">2. Accepting these terms</h3>
        <p>You must accept these Terms of Service to create an account and use WeftMark. By clicking "I Accept," you agree to these terms.</p>
        <p>If you do not accept, you may choose to delete your account from the same screen. Deleting your account permanently removes all your data from our servers.</p>
      </section>

      <section>
        <h3 className="font-semibold">3. What WeftMark is</h3>
        <p>WeftMark is a web application for weavers that lets you upload and view WIF weaving draft files, track weaving activities pick by pick, manage your loom inventory and equipment, record yarn and material inventory, and upload photos of your work in progress.</p>
      </section>

      <section>
        <h3 className="font-semibold">4. Your account</h3>
        <p>You sign in using a third-party identity provider (currently Google). We do not store your password — authentication is handled entirely by the provider you choose. You are responsible for the security of your account.</p>
      </section>

      <section>
        <h3 className="font-semibold">5. Content license</h3>
        <p>You retain ownership of the content you upload to WeftMark, including WIF files, designs, photos, and activity records.</p>
        <p>By uploading content to WeftMark, you grant WeftMark a <strong>worldwide, royalty-free, perpetual, irrevocable, non-exclusive license</strong> to store, process, display, reproduce, and use that content for any purpose related to operating, improving, or developing the platform, including but not limited to AI and machine learning model training, feature development, and quality assurance.</p>
        <p>This license survives account deletion. We will not sell your raw content to third parties.</p>
      </section>

      <section>
        <h3 className="font-semibold">6. What data we collect</h3>
        <p>When you use WeftMark, we collect your email address and display name (from your identity provider), the content you create and upload, settings and tags you assign to your content, and basic usage information such as when you last used the platform.</p>
      </section>

      <section>
        <h3 className="font-semibold">7. How we use your data</h3>
        <p>We use your data to provide the WeftMark service, keep your account secure, diagnose technical problems, improve platform features, and train AI and machine learning models (see section 8). We do not sell your data to anyone, share your data with advertisers, or use your data for advertising targeting.</p>
      </section>

      <section>
        <h3 className="font-semibold">8. AI and machine learning — opt-out</h3>
        <p>By default, your content, settings, and metadata — including WIF files, photos, activity data, loom configurations, tags, and any other data you create on the platform — <strong>may be used for AI and machine learning model training and feature improvements</strong>.</p>
        <p>You can opt out at any time from <strong>Settings → Privacy &amp; data</strong>. Opting out stops future use of your data for AI/ML training and disables public sharing links on your account. It does not retroactively remove data already used in model training. You can opt back in at any time.</p>
      </section>

      <section>
        <h3 className="font-semibold">9. Public sharing</h3>
        <p>WeftMark may offer optional public sharing links for weaving projects. Sharing is opt-in and per-project. If you have opted out of data use, public sharing links will not be accessible.</p>
      </section>

      <section>
        <h3 className="font-semibold">10. Data deletion</h3>
        <p>You can permanently delete your account and all associated data at any time from your settings page. Deletion removes your content from active storage and is irreversible. Some data may remain in database backups for up to 30 days. The content license granted prior to deletion survives for content already incorporated into model training or development artifacts.</p>
      </section>

      <section>
        <h3 className="font-semibold">11. Uptime and service availability</h3>
        <p>WeftMark is a hobby project. We do not promise any specific uptime or that the service will run indefinitely. We are not responsible for any loss of work or other consequences of service interruption.</p>
      </section>

      <section>
        <h3 className="font-semibold">12. Acceptable use</h3>
        <p>You agree not to use WeftMark for any illegal purpose, upload content you do not own, attempt to access other users' data, use automated tools to scrape content, or use the platform to harass or harm others. We reserve the right to suspend accounts that violate these rules.</p>
      </section>

      <section>
        <h3 className="font-semibold">13. Limitation of liability</h3>
        <p>WeftMark is provided "as is" without warranty of any kind. Our total liability to you for any claim is limited to zero dollars. This is a free hobby service.</p>
      </section>

      <section>
        <h3 className="font-semibold">14. Changes to these terms</h3>
        <p>When we update these terms, we will update the version number and require you to accept the updated terms before continuing to use the platform.</p>
      </section>

      <section>
        <h3 className="font-semibold">15. Contact</h3>
        <p>Questions about these terms or your data: <a href="mailto:hello@weftmark.com" className="underline">hello@weftmark.com</a></p>
      </section>

      <p className="text-xs text-muted-foreground pt-2 border-t">
        WeftMark is an independent hobby project built for weavers. It is not affiliated with any loom manufacturer, weaving organization, or software company.
      </p>
    </div>
  );
}
