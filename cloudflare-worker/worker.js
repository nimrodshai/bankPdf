/**
 * Cloudflare Worker - Telegram to GitHub Actions Bridge
 *
 * This worker receives Telegram webhook POSTs and triggers a GitHub Actions workflow.
 *
 * Required Environment Variables (set in Cloudflare dashboard):
 * - GITHUB_TOKEN: Personal Access Token with 'repo' scope
 * - GITHUB_OWNER: Your GitHub username
 * - GITHUB_REPO: Repository name
 * - TELEGRAM_SECRET: Optional secret to verify webhook authenticity
 */

export default {
  async fetch(request, env) {
    // Only accept POST requests
    if (request.method !== 'POST') {
      return new Response('OK', { status: 200 });
    }

    try {
      // Parse the Telegram update
      const update = await request.json();

      // Optional: Verify secret token from Telegram
      const secretHeader = request.headers.get('X-Telegram-Bot-Api-Secret-Token');
      if (env.TELEGRAM_SECRET && secretHeader !== env.TELEGRAM_SECRET) {
        return new Response('Unauthorized', { status: 401 });
      }

      // Trigger GitHub Actions workflow
      const response = await fetch(
        `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`,
        {
          method: 'POST',
          headers: {
            'Authorization': `token ${env.GITHUB_TOKEN}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'TelegramBot-CloudflareWorker',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            event_type: 'telegram-webhook',
            client_payload: {
              update: update
            }
          })
        }
      );

      if (!response.ok) {
        console.error('GitHub API error:', response.status, await response.text());
        return new Response('GitHub API error', { status: 500 });
      }

      return new Response('OK', { status: 200 });
    } catch (error) {
      console.error('Error:', error);
      return new Response('Error', { status: 500 });
    }
  }
};
