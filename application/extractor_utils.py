import re

class DataExtractor:
    @staticmethod
    def find_emails(text: str) -> list[str]:
        return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))

    @staticmethod
    def find_contacts(text: str) -> list[str]:
        # Pakistani aur international numbers ke liye basic regex
        return list(set(re.findall(r'\+?\d[\d\s-]{8,12}\d', text)))
    

    @staticmethod
    def find_social_links(links: list[str] | None) -> list[str]:
        if not links:
            return []
       
        social_domains = {'facebook.com', 'twitter.com', 'x.com', 'linkedin.com', 'instagram.com', 'youtube.com', "tiktok.com" ,"whatsapp.com" , "snapchat.com" , "telegram.org", "telegram.me", "pinterest.com", "github.com", "discord.gg", "twitch.tv" , "reddit.com" , "medium.com" , "shopify.com" , "wix.com" , "wordpress.com" , "squarespace.com" , "vimeo.com" , "soundcloud.com" , "behance.net" , "dribbble.com" , "tumblr.com" , "vk.com" , "ok.ru" , "vk.com" }
        social_links = list({
            link for link in links
            if any(domain in link.lower() for domain in social_domains)
        })
        
        return social_links
    