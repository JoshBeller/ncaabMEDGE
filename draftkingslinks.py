import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

def get_upcoming_games(driver, url, max_games=10):
    """Scrapes the main page for game links (Returns ALL games found up to max_games)."""
    print(f"\n=== SCRAPING GAMES ===")
    print(f"Navigating to {url}...\n")
    
    wait = WebDriverWait(driver, 15)
    upcoming_games = []

    try:
        driver.get(url)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.event-nav-link")))
        time.sleep(3) 
        
        print("Scrolling to load games...")
        for _ in range(4):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(1)
            
        print("Scanning for matches...\n")
        
        link_xpath = "//a[contains(@class, 'event-nav-link') and contains(@href, '/event/')]"
        elements_count = len(driver.find_elements(By.XPATH, link_xpath))
        
        for i in range(elements_count):
            try:
                # Re-fetch elements on EVERY iteration to defeat StaleElementExceptions
                current_links = driver.find_elements(By.XPATH, link_xpath)
                if i >= len(current_links):
                    break
                    
                link = current_links[i]
                href = link.get_attribute("href")
                
                # Parse the URL directly to get the team names (Skipping all DOM text checks)
                base_href = href.split('?')[0]
                url_slug = base_href.split('/event/')[1].split('/')[0]
                clean_slug = url_slug.replace('%2540', '@').replace('%40', '@')
                
                if '-@-' in clean_slug:
                    teams = clean_slug.split('-@-')
                else:
                    teams = clean_slug.split('@')

                away_team = teams[0].replace('-', ' ').strip().title()
                home_team = teams[1].replace('-', ' ').strip().title()
                matchup = f"{away_team} @ {home_team}"
                
                if not any(game['matchup'] == matchup for game in upcoming_games):
                    upcoming_games.append({
                        "matchup": matchup,
                        "link": base_href
                    })
                    
                if len(upcoming_games) >= max_games:
                    break
                    
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
                
        print(f"✅ Found {len(upcoming_games)} Games.\n")

    except Exception as e:
        print(f"❌ An error occurred while scraping links: {e}")
        
    return upcoming_games


if __name__ == "__main__":
    TARGET_URL = "https://sportsbook.draftkings.com/leagues/basketball/ncaab?category=game-lines&subcategory=all"
    
    print("Booting up Chrome...")
    test_driver = webdriver.Chrome()
    test_driver.maximize_window()
    
    try:
        # Test the function by passing the test_driver
        upcoming_list = get_upcoming_games(test_driver, TARGET_URL, max_games=10)
        
        # Print the results nicely
        for i, game in enumerate(upcoming_list, start=1):
            print(f"{i}. {game['matchup']}")
            print(f"   Link: {game['link']}\n")
            
    finally:
        test_driver.quit()