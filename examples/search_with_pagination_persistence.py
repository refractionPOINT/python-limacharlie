#!/usr/bin/env python3
"""
Example: Search API with Pagination Persistence

Demonstrates how to use the Search API with pagination state persistence,
allowing resumption from a specific page if the search is interrupted.

Parameters:
    None

Return:
    None
"""

import json
from limacharlie import Manager

# State file to persist pagination progress
STATE_FILE = 'search_state.json'

def save_state(query_id, page_number, next_token):
    """
    Save pagination state to disk for resumption.

    Parameters:
        query_id (str): The search query ID.
        page_number (int): The current page number.
        next_token (str): The token to resume from.

    Return:
        None
    """
    state = {
        'query_id': query_id,
        'page_number': page_number,
        'next_token': next_token
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)
    print(f"Saved state: page {page_number}, token={next_token[:20] if next_token else 'None'}...", flush=True)

def load_state():
    """
    Load pagination state from disk.

    Parameters:
        None

    Return:
        dict or None: The saved state, or None if no state file exists.
    """
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            print(f"Loaded state: page {state['page_number']}, token={state['next_token'][:20] if state['next_token'] else 'None'}...")
            return state
    except FileNotFoundError:
        return None

def main():
    """
    Main function demonstrating pagination persistence.

    Parameters:
        None

    Return:
        None
    """
    # Create manager instance
    manager = Manager()

    # Define search parameters
    query = "event_type = NEW_PROCESS"
    start_time = 1733990000  # Example timestamp
    end_time = 1734076400    # Example timestamp

    # Try to load previous state
    saved_state = load_state()

    if saved_state:
        print(f"Resuming from page {saved_state['page_number']}...")
        query_id = saved_state['query_id']
        resume_token = saved_state['next_token']
    else:
        print("Starting new search...")
        query_id = None
        resume_token = None

    # Track query_id when initiated
    def on_query_initiated(qid):
        print(f"Search initiated with query_id: {qid}")
        # Save initial state with query_id
        save_state(qid, 0, None)

    # Persist pagination state after each page
    def on_page_completed(page_number, next_token):
        # Save state so we can resume from this point
        current_query_id = query_id if query_id else saved_state['query_id']
        save_state(current_query_id, page_number, next_token)

    try:
        # Execute search with pagination persistence
        event_count = 0
        for result in manager.executeSearch(
            query,
            start_time,
            end_time,
            query_id=query_id,
            resume_token=resume_token,
            on_query_initiated=on_query_initiated,
            on_page_completed=on_page_completed
        ):
            result_type = result.get('type', 'unknown')
            page_number = result.get('_page_number', 0)

            if result_type == 'events':
                rows = result.get('rows', [])
                event_count += len(rows)
                print(f"Page {page_number}: Received {len(rows)} events (total: {event_count})")

        print(f"\nSearch completed successfully! Total events: {event_count}")

        # Clean up state file on successful completion
        import os
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print("State file cleaned up.")

    except KeyboardInterrupt:
        print("\n\nSearch interrupted by user.")
        print(f"Progress has been saved to {STATE_FILE}")
        print("Run this script again to resume from where you left off.")
    except Exception as e:
        print(f"\nError during search: {e}")
        print(f"Progress has been saved to {STATE_FILE}")
        print("Run this script again to resume from where you left off.")

if __name__ == '__main__':
    main()
