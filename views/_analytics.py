"""
_analytics — PostHog page-view tracking for Streamlit.

Streamlit is a single-page app under the hood: clicking "Hotspots" in the
sidebar re-renders the page but doesn't change the URL. Analytics tools
see one page unless we explicitly tell them otherwise.

This module solves that by injecting a small PostHog snippet on every page
render, calling posthog.capture('$pageview', {page: 'Hotspots'}) with the
current page's name. That gives us real page-level analytics despite the
SPA architecture.

The tracker is silently no-op'd if POSTHOG_API_KEY isn't configured —
matching the same graceful-degradation pattern as the AI helpers.

Usage: in each page (view file), add near the top:
    from views._analytics import track_page
    track_page("Hotspots")
"""

import streamlit as st
import streamlit.components.v1 as components


def _get_config():
    """Return (api_key, host) or (None, None) if analytics isn't configured."""
    try:
        api_key = st.secrets.get("POSTHOG_API_KEY")
        host = st.secrets.get("POSTHOG_HOST", "https://us.i.posthog.com")
        if not api_key:
            return None, None
        return api_key, host
    except Exception:
        return None, None


def is_analytics_enabled() -> bool:
    """True iff PostHog is configured. Same pattern as is_ai_enabled()."""
    api_key, _ = _get_config()
    return api_key is not None


def track_page(page_name: str) -> None:
    """Fire a $pageview event to PostHog for the given page.

    Called at the top of each Streamlit page. Silently no-op if PostHog
    isn't configured, so the app still works fine without analytics.

    Notes on how this works:
      * Streamlit renders our HTML inside an iframe. The PostHog snippet
        runs inside the iframe context, but the parent URL is captured
        via document.referrer, which PostHog uses for source attribution.
      * We call posthog.capture() explicitly with a page name rather than
        relying on posthog's autocapture, because autocapture would see
        every Streamlit page as the same URL.
      * The component height is 0 so the tracking iframe doesn't affect
        page layout.
    """
    api_key, host = _get_config()
    if api_key is None:
        return

    # The PostHog snippet initialises with our API key, then immediately
    # fires a $pageview event with the page name in properties. Also
    # captures the current session_id so PostHog groups events into
    # sessions correctly.
    tracking_html = f"""
    <script>
        !function(t,e){{var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){{function g(t,e){{var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}}(p=t.createElement("script")).type="text/javascript",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){{var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e}},u.people.toString=function(){{return u.toString(1)+".people (stub)"}},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])}},e.__SV=1)}}(document,window.posthog||[]);
        posthog.init('{api_key}', {{
            api_host: '{host}',
            capture_pageview: false
        }});
        posthog.capture('$pageview', {{
            page: '{page_name}',
            $current_url: 'https://okr-planning-app.streamlit.app/#{page_name.lower().replace(" ", "-")}'
        }});
    </script>
    """
    components.html(tracking_html, height=0)
