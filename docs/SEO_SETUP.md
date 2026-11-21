# Cendavo search indexing launch checklist

The intended public search domain is **https://cendavo.au/**. Cloudflare's `cendavo-deployment.pages.dev` address remains a technical deployment/preview address, not the preferred search URL.

## 1. Make sure the custom domain works *before* merging the SEO branch

In Cloudflare Dashboard → Workers & Pages → **cendavo-deployment** → Custom domains, check that `cendavo.au` is attached, active and serving the production deployment. Confirm that DNS and TLS work.

Visit all three in an incognito browser (or run the commands below):

```sh
curl -IL https://cendavo.au/
curl -IL https://cendavo.au/robots.txt
curl -IL https://cendavo.au/sitemap.xml
```

They should load successfully; the main page should render normally, and `robots.txt` should declare `Sitemap: https://cendavo.au/sitemap.xml`. If any page fails to resolve or returns an error, **fix Cloudflare custom-domain/DNS configuration before merging**. This repository change does not itself change DNS or connect a Cloudflare custom domain.

Choose `https://cendavo.au` as the primary hostname. Set up an appropriate Cloudflare redirect from `www.cendavo.au` to `cendavo.au` if the www hostname is configured, preserving the request path. Do not blanket-redirect `*.pages.dev` without checking that existing preview links continue to work.

## 2. Publish the revised canonical origin

After the custom domain works and the owner approves the change, merge this branch to `main`. The Git-linked Cloudflare Pages build runs `python3 scripts/build_site.py`; that automatically generates the following from one `BASE_URL`:

- Public-page canonical links and Open Graph share URLs pointing to `https://cendavo.au`
- Homepage schema.org `ProfessionalService.url` pointing to `https://cendavo.au/`
- `/robots.txt`, allowing public crawling and referencing the Cendavo sitemap
- `/sitemap.xml`, containing the seven public routes (Home, Work, Services, Pricing, Demo, About, Contact); the 404 page is excluded

After production deployment, inspect page source for canonical URLs. Avoid `noindex` on public pages. Do not add invented case studies or fictitious client reviews for search optimisation.

## 3. Register with search engines

**Google Search Console**

1. Open https://search.google.com/search-console/
2. Add the **Domain** property `cendavo.au`. Verify the DNS TXT record Google gives you with the DNS provider.
3. Open **Sitemaps** and submit `https://cendavo.au/sitemap.xml` (or enter `sitemap.xml` in the property-specific input).
4. Use **URL Inspection** for `https://cendavo.au/`, check that it can be indexed and request indexing after the canonical-origin deployment.
5. Inspect **Pages** reports for redirects, blocked pages, `noindex`, `404`, server errors and Google-chosen canonicals. Submission does not guarantee indexing.

**Bing Webmaster Tools**

1. Visit https://www.bing.com/webmasters/
2. Import the verified Search Console property or verify the site separately.
3. Check that the sitemap is registered. If not, submit `https://cendavo.au/sitemap.xml`.

## 4. Improve search visibility beyond technical discovery

- Strengthen dedicated, genuinely useful service pages for search intents such as Sydney website design, redesign and website maintenance. Use local evidence and useful FAQs rather than repeating the same keyword across thin suburb pages.
- Add real customer projects, accurate descriptions and testimonials **only after client permission**.
- Maintain a legitimate Google Business Profile if the business satisfies Google's eligibility requirements; configure the service area accurately.
- Connect relevant business listings/social profiles to the canonical URL, and earn genuine local links.
- Track search impressions, clicks, indexing errors and enquiries through Search Console and the business's own analytics.

Google's instructions: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap

*Note:* The current sitemap's `lastmod` is the build date. For greater precision later, change it to the actual date of significant content updates for each page (or omit the optional field); a rebuild without page changes is not a meaningful modification date.
