import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def clear_betslip(driver):
    """Loops and forces DraftKings to clear the betslip by clicking the individual 'X' buttons."""
    print("   -> Clearing betslip and waiting for confirmation...")
    
    for attempt in range(5): 
        # Target the individual "X" icons directly
        close_buttons = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='betslip-selection-card-ex-button']")
        if not close_buttons:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Close']")
            
        # IF THE BETSLIP IS EMPTY, BREAK THE LOOP AND PROCEED!
        if len(close_buttons) == 0:
            return 
            
        # If not empty, click them all
        for btn in close_buttons:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5) 
            except Exception:
                continue
                
        time.sleep(1) # Wait for the animations to finish before checking again
        
    print("   -> Warning: Betslip might not be fully clear, proceeding anyway.")


def parse_odds(odds_text):
    """Helper function to convert string odds like '−150' or '+200' into integers for comparison."""
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


def build_all_sgps(url):
    print("=== DraftKings 4-Way Master SGP Automator ===")
    print("Launching Chrome...\n")
    
    driver = webdriver.Chrome()
    driver.maximize_window()
    wait = WebDriverWait(driver, 15)

    try:
        base_url = url.split('?')[0]
        
        # --- PRE-STEP: Determine Away and Home Teams ---
        clean_slug = base_url.split('/event/')[1].split('/')[0].replace('%2540', '@').replace('%40', '@')
        away_part, home_part = clean_slug.split('-@-') if '-@-' in clean_slug else clean_slug.split('@')
        
        away_team = away_part.replace('-', ' ').strip().title()
        home_team = home_part.replace('-', ' ').strip().title()
        
        # Grab the FIRST word of the team name to search the DOM
        away_keyword = away_team.split()[0]
        home_keyword = home_team.split()[0]

        print(f"Navigating to {base_url} to analyze odds...")
        driver.get(base_url)
        time.sleep(3)
        
        # --- PRE-STEP: Determine Favorite vs Underdog & Grab Single ML Odds ---
        grid_xpath = "//div[contains(@class, 'cb-side-column__right--vertical')]"
        wait.until(EC.presence_of_element_located((By.XPATH, grid_xpath)))
        wait.until(lambda d: len(d.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")) >= 6)
        odds_buttons = driver.find_elements(By.XPATH, f"{grid_xpath}//button[@data-testid='component-builder-market-button']")
        
        away_odds_val = parse_odds(odds_buttons[2].text)
        home_odds_val = parse_odds(odds_buttons[5].text)
        
        # Extract the exact string (e.g., "-110") from the button text
        away_ml_str = odds_buttons[2].text.split('\n')[-1]
        home_ml_str = odds_buttons[5].text.split('\n')[-1]
        
        if away_odds_val < home_odds_val:
            fav_ml_idx, fav_keyword, fav_team = 2, away_keyword, away_team
            dog_ml_idx, dog_keyword, dog_team = 5, home_keyword, home_team
            fav_ml_odds, dog_ml_odds = away_ml_str, home_ml_str
            print(f"⭐ Favorite: {fav_team} ({fav_ml_odds})")
            print(f"🐕 Underdog: {dog_team} ({dog_ml_odds})\n")
        else:
            fav_ml_idx, fav_keyword, fav_team = 5, home_keyword, home_team
            dog_ml_idx, dog_keyword, dog_team = 2, away_keyword, away_team
            fav_ml_odds, dog_ml_odds = home_ml_str, away_ml_str
            print(f"⭐ Favorite: {fav_team} ({fav_ml_odds})")
            print(f"🐕 Underdog: {dog_team} ({dog_ml_odds})\n")

        # Define ALL 4 combinations tracking their IDs for the final output
        combinations = [
            {"id": "fm_fo", "name": f"Favorite ML + Favorite OVER", "ml_idx": fav_ml_idx, "team_keyword": fav_keyword},
            {"id": "um_uo", "name": f"Underdog ML + Underdog OVER", "ml_idx": dog_ml_idx, "team_keyword": dog_keyword},
            {"id": "fm_uo", "name": f"Favorite ML + Underdog OVER", "ml_idx": fav_ml_idx, "team_keyword": dog_keyword},
            {"id": "um_fo", "name": f"Underdog ML + Favorite OVER", "ml_idx": dog_ml_idx, "team_keyword": fav_keyword}
        ]

        results = {}
        fav_over_odds = "N/A"
        dog_over_odds = "N/A"

        # --- EXECUTE THE 4 PARLAYS ---
        for combo in combinations:
            print(f"--- Building: {combo['name']} ---")
            
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
            
            # Find the specific row for this team and click OVER
            buttons_xpath = f"//div[@data-testid='market-template' and .//*[contains(text(), '{combo['team_keyword']}') and contains(text(), 'Team Total Points')]]//button[@data-testid='component-builder-market-button']"
            wait.until(EC.presence_of_element_located((By.XPATH, buttons_xpath)))
            prop_buttons = driver.find_elements(By.XPATH, buttons_xpath)
            
            if len(prop_buttons) >= 2:
                over_btn = prop_buttons[0] # Button 0 is OVER
                
                # Grab the single "Over" odds text before clicking
                over_odds_str = over_btn.text.split('\n')[-1]
                if combo["team_keyword"] == fav_keyword:
                    fav_over_odds = over_odds_str
                else:
                    dog_over_odds = over_odds_str

                click_and_verify(driver, wait, over_btn, "Team Total OVER")
            else:
                print("⚠️ Could not find Over button.")
                clear_betslip(driver)
                continue
                
            time.sleep(4) 
            try:
                odds_css = "div[data-testid='betslip-odds-standard'] span.sportsbook-odds"
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, odds_css)))
                all_betslip_odds = driver.find_elements(By.CSS_SELECTOR, odds_css)
                
                if all_betslip_odds:
                    sgp_odds = all_betslip_odds[-1].text
                    print(f"✅ Odds retrieved: {sgp_odds}")
                    results[combo['id']] = sgp_odds
                else:
                    results[combo['id']] = "N/A"
            except Exception:
                results[combo['id']] = "Failed to calculate"

            clear_betslip(driver)
            print("")

        # --- FINAL FORMATTED SUMMARY ---
        print("\n==================================")
        print("🏆 4-WAY MASTER SGP SUMMARY 🏆")
        print("==================================")
        print(f"Favorite Moneyline ({fav_team}): {fav_ml_odds}")
        print(f"Underdog Moneyline ({dog_team}): {dog_ml_odds}")
        print(f"Favorite Over ({fav_team}): {fav_over_odds}")
        print(f"Underdog Over ({dog_team}): {dog_over_odds}")
        print("-" * 34)
        print(f"fm + fo: {results.get('fm_fo', 'N/A')}")
        print(f"um + uo: {results.get('um_uo', 'N/A')}")
        print(f"fm + uo: {results.get('fm_uo', 'N/A')}")
        print(f"um + fo: {results.get('um_fo', 'N/A')}")
        print("==================================\n")

    except Exception as e:
        print(f"\n❌ Script failed: {e}")

    finally:
        input("\nPress Enter in the console to close the browser...")
        driver.quit()

if __name__ == "__main__":
    TARGET_URL = "https://sportsbook.draftkings.com/event/st.-johns-%2540-kansas/33852812?"
    build_all_sgps(TARGET_URL)