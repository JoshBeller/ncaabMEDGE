import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def clear_betslip(driver):
    """Loops and forces DraftKings to clear the betslip by clicking the individual 'X' buttons."""
    print("   -> Clearing betslip and waiting for confirmation...")
    for attempt in range(5): 
        close_buttons = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='betslip-selection-card-ex-button']")
        if not close_buttons:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Close']")
            
        if len(close_buttons) == 0:
            return 
            
        for btn in close_buttons:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5) 
            except Exception:
                continue
                
        time.sleep(1) 
    print("   -> Warning: Betslip might not be fully clear, proceeding anyway.")

def parse_odds(odds_text):
    """Helper function to convert string odds into integers for comparison."""
    clean_text = odds_text.replace('−', '-').replace('\n', '').strip()
    if not clean_text: return 0
    if clean_text.upper() == "EVEN": return 100
    try:
        return int(clean_text)
    except:
        return 0

def click_and_verify(driver, wait, button_element, name_for_log):
    """Clicks a button and validates that DraftKings actually registered the selection."""
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button_element)
    time.sleep(1) 
    
    driver.execute_script("arguments[0].click();", button_element)
    
    try:
        wait.until(lambda d: "selected" in button_element.get_attribute("class") or button_element.get_attribute("aria-pressed") == "true")
    except:
        print(f"   -> DraftKings ignored the {name_for_log} click. Retrying...")
        driver.execute_script("arguments[0].click();", button_element)
        time.sleep(1.5)

# ==========================================
# PHASE 1: UPCOMING GAMES SCRAPER (FIXED)
# ==========================================

def get_upcoming_games(driver, url, max_games=10):
    """Scrapes the main page for 'Today's' game links by iterating over the links directly."""
    print(f"\n=== SCRAPING GAMES ===")
    print(f"Navigating to {url}...\n")
    
    wait = WebDriverWait(driver, 15)
    upcoming_games = []

    try:
        driver.get(url)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='lp-nav-link']")))
        time.sleep(3) 
        
        print("Scrolling to load games...")
        for _ in range(4):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(1)
            
        print("Scanning for 'Today' matches...\n")
        
        # Target the specific 'More Bets' links directly (1 per game)
        link_xpath = "//a[@data-testid='lp-nav-link']"
        elements_count = len(driver.find_elements(By.XPATH, link_xpath))
        
        for i in range(elements_count):
            try:
                current_links = driver.find_elements(By.XPATH, link_xpath)
                if i >= len(current_links):
                    break
                    
                link = current_links[i]
                
                # 1. Traverse up to the container that holds BOTH the link and the start time
                try:
                    row_container = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'cb-static-parlay__content--inner')][1]")
                    time_elem = row_container.find_element(By.CSS_SELECTOR, "span[data-testid='cb-event-cell__start-time']")
                    time_text = time_elem.text.lower()
                except:
                    # If there's no start time (e.g. game is Live and showing a clock), skip it
                    continue
                
                # 2. Filter logic: MUST explicitly say "today"
                if "today" not in time_text:
                    continue

                # 3. If it passed, process the URL
                href = link.get_attribute("href")
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
                
        print(f"✅ Found {len(upcoming_games)} 'Today' Games.\n")

    except Exception as e:
        print(f"❌ An error occurred while scraping links: {e}")
        
    return upcoming_games

# ==========================================
# PHASE 2: 4-WAY SGP BUILDER
# ==========================================

def build_all_sgps(driver, url):
    """Takes the shared driver and a single game URL, calculates the 4 SGPs, and returns the stats."""
    wait = WebDriverWait(driver, 15)
    
    game_data = {
        "fav_team": "", "fav_ml": "N/A", "fav_over": "N/A",
        "dog_team": "", "dog_ml": "N/A", "dog_over": "N/A",
        "combos": {"fm_fo": "N/A", "um_uo": "N/A", "fm_uo": "N/A", "um_fo": "N/A"}
    }

    try:
        base_url = url.split('?')[0]
        
        clean_slug = base_url.split('/event/')[1].split('/')[0].replace('%2540', '@').replace('%40', '@')
        away_part, home_part = clean_slug.split('-@-') if '-@-' in clean_slug else clean_slug.split('@')
        
        away_team = away_part.replace('-', ' ').strip().title()
        home_team = home_part.replace('-', ' ').strip().title()
        
        away_keyword = away_team.split()[0]
        home_keyword = home_team.split()[0]

        print(f"Navigating to {base_url} to analyze odds...")
        driver.get(base_url)
        time.sleep(3)
        
        grid_xpath = "//div[contains(@class, 'cb-side-column__right--vertical')]"
        wait.until(EC.presence_of_element_located((By.XPATH, grid_xpath)))
        wait.until(lambda d: len(d.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")) >= 6)
        odds_buttons = driver.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")
        
        away_odds_val = parse_odds(odds_buttons[2].text)
        home_odds_val = parse_odds(odds_buttons[5].text)
        
        away_ml_str = odds_buttons[2].text.split('\n')[-1]
        home_ml_str = odds_buttons[5].text.split('\n')[-1]
        
        if away_odds_val < home_odds_val:
            fav_ml_idx, fav_keyword, fav_team = 2, away_keyword, away_team
            dog_ml_idx, dog_keyword, dog_team = 5, home_keyword, home_team
            fav_ml_odds, dog_ml_odds = away_ml_str, home_ml_str
        else:
            fav_ml_idx, fav_keyword, fav_team = 5, home_keyword, home_team
            dog_ml_idx, dog_keyword, dog_team = 2, away_keyword, away_team
            fav_ml_odds, dog_ml_odds = home_ml_str, away_ml_str

        print(f"⭐ Favorite: {fav_team} ({fav_ml_odds}) | 🐕 Underdog: {dog_team} ({dog_ml_odds})")

        game_data["fav_team"] = fav_team
        game_data["fav_ml"] = fav_ml_odds
        game_data["dog_team"] = dog_team
        game_data["dog_ml"] = dog_ml_odds

        combinations = [
            {"id": "fm_fo", "name": f"Favorite ML + Favorite OVER", "ml_idx": fav_ml_idx, "team_keyword": fav_keyword},
            {"id": "um_uo", "name": f"Underdog ML + Underdog OVER", "ml_idx": dog_ml_idx, "team_keyword": dog_keyword},
            {"id": "fm_uo", "name": f"Favorite ML + Underdog OVER", "ml_idx": fav_ml_idx, "team_keyword": dog_keyword},
            {"id": "um_fo", "name": f"Underdog ML + Favorite OVER", "ml_idx": dog_ml_idx, "team_keyword": fav_keyword}
        ]

        # --- EXECUTE THE 4 PARLAYS ---
        for combo in combinations:
            print(f"   --- Building: {combo['name']} ---")
            
            driver.get(base_url)
            time.sleep(0.5)
            
            wait.until(EC.presence_of_element_located((By.XPATH, grid_xpath)))
            wait.until(lambda d: len(d.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")) >= 6)
            odds_buttons = driver.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")
            
            ml_btn = odds_buttons[combo["ml_idx"]]
            click_and_verify(driver, wait, ml_btn, "Moneyline")
            time.sleep(0.5) 
            
            props_url = f"{base_url}?category=all-odds&subcategory=team-props"
            driver.get(props_url)
            time.sleep(0.5)
            
            buttons_xpath = f"//div[@data-testid='market-template' and .//*[contains(text(), '{combo['team_keyword']}') and contains(text(), 'Team Total Points')]]//button[@data-testid='component-builder-market-button']"
            wait.until(EC.presence_of_element_located((By.XPATH, buttons_xpath)))
            prop_buttons = driver.find_elements(By.XPATH, buttons_xpath)
            
            if len(prop_buttons) >= 2:
                over_btn = prop_buttons[0] 
                
                over_odds_str = over_btn.text.split('\n')[-1]
                if combo["team_keyword"] == fav_keyword:
                    game_data["fav_over"] = over_odds_str
                else:
                    game_data["dog_over"] = over_odds_str

                click_and_verify(driver, wait, over_btn, "Team Total OVER")
            else:
                print("   ⚠️ Could not find Over button.")
                clear_betslip(driver)
                continue
                
            time.sleep(4) 
            try:
                odds_css = "div[data-testid='betslip-odds-standard'] span.sportsbook-odds"
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, odds_css)))
                all_betslip_odds = driver.find_elements(By.CSS_SELECTOR, odds_css)
                
                if all_betslip_odds:
                    sgp_odds = all_betslip_odds[-1].text
                    print(f"   ✅ Odds retrieved: {sgp_odds}")
                    game_data["combos"][combo['id']] = sgp_odds
            except Exception:
                pass

            clear_betslip(driver)
            print("")

    except Exception as e:
        print(f"\n   ❌ Failed to process game: {e}")

    return game_data

# ==========================================
# MASTER RUNNER
# ==========================================

def main():
    TARGET_URL = "https://sportsbook.draftkings.com/leagues/basketball/ncaab?category=game-lines&subcategory=all"
    
    print("Booting up Master Chrome Driver...\n")
    driver = webdriver.Chrome()
    driver.maximize_window()
    
    mega_results = {}

    try:
        # Grab up to 10 "Today" games
        games_array = get_upcoming_games(driver, TARGET_URL, max_games=10)
        
        if not games_array:
            print("No games found to process. Exiting.")
            return

        # Loop through every game and process the SGPs
        for game in games_array:
            print(f"\n==========================================")
            print(f" STARTING NEW MATCHUP: {game['matchup']}")
            print(f"==========================================")
            
            data = build_all_sgps(driver, game['link'])
            mega_results[game['matchup']] = data

        # Print the massive final report
        print("\n\n" + "="*50)
        print("🏆 MEGA MASTER SGP SUMMARY 🏆")
        print("="*50)
        
        for matchup, data in mega_results.items():
            print(f"\n🏀 {matchup}")
            if data["fav_team"] == "":
                print("   -> Failed to retrieve odds.")
                continue
                
            print(f"   Favorite Moneyline ({data['fav_team']}): {data['fav_ml']}")
            print(f"   Underdog Moneyline ({data['dog_team']}): {data['dog_ml']}")
            print(f"   Favorite Over ({data['fav_team']}): {data['fav_over']}")
            print(f"   Underdog Over ({data['dog_team']}): {data['dog_over']}")
            print("   " + "-"*34)
            print(f"   fm + fo: {data['combos']['fm_fo']}")
            print(f"   um + uo: {data['combos']['um_uo']}")
            print(f"   fm + uo: {data['combos']['fm_uo']}")
            print(f"   um + fo: {data['combos']['um_fo']}")

    finally:
        input("\nPress Enter in the console to close the browser...")
        driver.quit()

if __name__ == "__main__":
    main()