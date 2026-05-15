import amazonLogo from "../../../assets/channel-logos/amazon.svg";
import beehiivLogo from "../../../assets/channel-logos/beehiiv.svg";
import facebookLogo from "../../../assets/channel-logos/facebook.svg";
import googleLogo from "../../../assets/channel-logos/google.svg";
import instagramLogo from "../../../assets/channel-logos/instagram.svg";
import linkedinLogo from "../../../assets/channel-logos/linkedin.svg";
import liveintentLogo from "../../../assets/channel-logos/liveintent.svg";
import metaLogo from "../../../assets/channel-logos/meta.svg";
import molocoLogo from "../../../assets/channel-logos/moloco.svg";
import snapchatLogo from "../../../assets/channel-logos/snapchat.svg";
import tiktokLogo from "../../../assets/channel-logos/tiktok.svg";

const channelAliases: Record<string, string> = {
  fb: "facebook",
  facebook: "facebook",
  ig: "instagram",
  insta: "instagram",
  instagram: "instagram",
  google_ads: "google",
  googleads: "google",
  linked_in: "linkedin",
  linkedin: "linkedin",
};

export const nonMediaChannelPrefixes = new Set([
  "all",
  "aggregate",
  "kpi",
  "outcome",
  "overall",
  "revenue",
  "sales",
  "subtotal",
  "sum",
  "total",
]);

export const channelLogoRegistry: Record<string, string> = {
  amazon: amazonLogo,
  beehiiv: beehiivLogo,
  facebook: facebookLogo,
  google: googleLogo,
  instagram: instagramLogo,
  linkedin: linkedinLogo,
  liveintent: liveintentLogo,
  meta: metaLogo,
  moloco: molocoLogo,
  snapchat: snapchatLogo,
  tiktok: tiktokLogo,
};

export function normalizeChannelName(value: string) {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
  const aliasKey = normalized.replace(/_/g, "");
  return channelAliases[normalized] ?? channelAliases[aliasKey] ?? normalized;
}

export function isValidMediaChannel(value: string) {
  const normalized = normalizeChannelName(value);
  return Boolean(normalized) && !nonMediaChannelPrefixes.has(normalized);
}

export function displayChannelName(value: string) {
  const normalized = normalizeChannelName(value);
  const labels: Record<string, string> = {
    amazon: "Amazon",
    beehiiv: "beehiiv",
    facebook: "Facebook",
    google: "Google",
    instagram: "Instagram",
    linkedin: "LinkedIn",
    liveintent: "LiveIntent",
    meta: "Meta",
    moloco: "Moloco",
    snapchat: "Snapchat",
    tiktok: "TikTok",
  };
  return labels[normalized] ?? value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function initialsForChannel(value: string) {
  const words = displayChannelName(value).match(/[A-Za-z0-9]+/g) ?? [];
  if (!words.length) {
    return "?";
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
}

export function ChannelLogo({ channel }: { channel: string }) {
  const normalized = normalizeChannelName(channel);
  const logo = channelLogoRegistry[normalized];
  const logoClass = logo ? "prior-brand-mark--logo" : "prior-brand-mark--fallback";
  return (
    <span className={`prior-brand-mark prior-brand-mark--${normalized || "fallback"} ${logoClass}`}>
      {logo ? <img alt="" aria-hidden="true" src={logo} /> : initialsForChannel(channel)}
    </span>
  );
}
