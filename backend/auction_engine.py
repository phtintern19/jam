import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import or_
from database import SessionLocal
import models
import schemas

logger = logging.getLogger(__name__)

async def auction_engine_loop():
    """
    Background loop that runs periodically to manage auction states.
    """
    logger.info("Starting background auction engine loop...")
    while True:
        try:
            await manage_auctions()
        except Exception as e:
            logger.error(f"Error in auction engine loop: {e}", exc_info=True)
        
        # Run every 5 seconds for responsive transitions
        await asyncio.sleep(5)

async def manage_auctions():
    """
    Core logic to transition events and auctions.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        
        # 1. Auto-start scheduled auctions
        upcoming_events = db.query(models.Event).filter(
            models.Event.start_date <= now,
            models.Event.status == 'upcoming'
        ).all()
        
        for event in upcoming_events:
            logger.info(f"Auto-starting auction for event: {event.title} (ID: {event.event_id})")
            event.status = 'in_progress'
            event.is_live = True
            
            # Check if auction already exists, if not create one
            auction = db.query(models.Auction).filter(models.Auction.event_id == event.event_id).first()
            if not auction:
                # Ensure end_time is after start_time to satisfy check constraint
                auction_end_time = event.end_date
                if auction_end_time <= event.start_date:
                    auction_end_time = event.start_date + timedelta(hours=1)
                
                auction = models.Auction(
                    event_id=event.event_id,
                    creator_id=event.creator_id,
                    title=f"{event.title} Auction",
                    start_time=event.start_date,
                    end_time=auction_end_time,
                    status='in_progress',
                    current_bid_amount=0
                )
                db.add(auction)
            else:
                auction.status = 'in_progress'
            
            db.commit()

        # 2. Manage active auctions
        active_auctions = db.query(models.Auction).filter(
            models.Auction.status == 'in_progress'
        ).all()
        print(f"DEBUG: Active auctions count: {len(active_auctions)}")
        
        for auction in active_auctions:
            event = auction.event
            if not event:
                continue

            print(f"DEBUG: Processing Auction {auction.auction_id}, Status: {auction.status}, Current Player: {auction.current_player_id}")
            # a. If no player is currently being auctioned, pick the next one
            if auction.current_player_id is None:
                # Subquery for already auctioned players in this auction
                auctioned_player_ids_q = db.query(models.Bid.player_id).filter(
                    models.Bid.auction_id == auction.auction_id
                ).distinct()
                auctioned_player_ids = [r[0] for r in auctioned_player_ids_q.all()]
                print(f"DEBUG: Auctioned Player IDs: {auctioned_player_ids}")
                logger.info(f"Auctioned Player IDs for auction {auction.auction_id}: {auctioned_player_ids}")

                next_player = db.query(models.Player).join(models.Player.events).filter(
                    models.Event.event_id == event.event_id,
                    ~models.Player.player_id.in_(auctioned_player_ids)
                ).first()

                if next_player:
                    print(f"DEBUG: Found next player: {next_player.full_name} (ID: {next_player.player_id})")
                    logger.info(f"Starting bidding for player: {next_player.full_name} (ID: {next_player.player_id}) in auction {auction.auction_id}")
                    auction.current_player_id = next_player.player_id
                    auction.current_player_bid_start = now
                    auction.current_bid_amount = event.base_prices.get('Standard', 0) if event.base_prices else 0
                    db.commit()
                else:
                    # No more players to auction
                    print("DEBUG: No more players found.")
                    logger.info(f"Auction {auction.auction_id} concluded. No more players.")
                    auction.status = 'completed'
                    event.status = 'completed'
                    event.is_live = False
                    db.commit()
            
            # b. If a player IS being auctioned, check if time is up
            else:
                bid_time_limit = event.bid_time_limit or 20
                time_passed = (now - auction.current_player_bid_start).total_seconds() if auction.current_player_bid_start else 0
                print(f"DEBUG: Time passed: {time_passed}, Limit: {bid_time_limit}")
                
                if auction.current_player_bid_start and time_passed >= bid_time_limit:
                    # Time is up! Process the result
                    process_bid_conclusion(db, auction)

    finally:
        db.close()

def start_auction_engine():
    """
    Entry point to start the auction engine in a background thread.
    """
    import threading
    
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auction_engine_loop())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    logger.info("Auction engine background thread started.")

def get_or_create_system_resources(db):
    """
    Ensure a system user, team owner, and team exist for 'unsold' bids.
    """
    # 1. System User
    system_user = db.query(models.User).filter(models.User.email == "system@bidzone.com").first()
    if not system_user:
        system_user = models.User(
            username="system_auction",
            email="system@bidzone.com",
            password_hash="system_password_hash_not_usable",
            user_type=models.UserType.admin, # Or special type if available
            is_active=False # Prevent login
        )
        db.add(system_user)
        db.flush()

    # 2. System Team Owner
    system_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == system_user.user_id).first()
    if not system_owner:
        system_owner = models.TeamOwner(
            user_id=system_user.user_id,
            owner_name="System Auctioneer"
        )
        db.add(system_owner)
        db.flush()

    # 3. System Team
    system_team = db.query(models.Team).filter(models.Team.owner_id == system_owner.team_owner_id).first()
    if not system_team:
        system_team = models.Team(
            team_name="Unsold Players",
            owner_id=system_owner.team_owner_id,
            status='inactive'
        )
        db.add(system_team)
        db.commit()
    
    return system_team

def process_bid_conclusion(db, auction):
    """
    Handle the end of a bidding phase for a player.
    """
    logger.info(f"Concluding bidding for player ID {auction.current_player_id} in auction {auction.auction_id}")
    
    # 1. Find the highest bid for this player in this auction
    highest_bid = db.query(models.Bid).filter(
        models.Bid.auction_id == auction.auction_id,
        models.Bid.player_id == auction.current_player_id
    ).order_by(models.Bid.amount.desc()).first()

    if highest_bid:
        # We have a winner!
        highest_bid.status = 'won'
        logger.info(f"Player {auction.current_player_id} won by team {highest_bid.team_id} for {highest_bid.amount}")
        
        # Deduct from team owner's wallet (simplified)
        team = highest_bid.team
        if team and team.owner:
            team.owner.wallet_balance -= highest_bid.amount
            
    else:
        # No bids, handle unsold
        logger.info(f"Player {auction.current_player_id} UNSOLD. Creating unsold record.")
        try:
            system_team = get_or_create_system_resources(db)
            unsold_bid = models.Bid(
                auction_id=auction.auction_id,
                player_id=auction.current_player_id,
                team_id=system_team.team_id,
                amount=0,
                status='unsold'
            )
            db.add(unsold_bid)
        except Exception as e:
            logger.error(f"Error creating unsold bid: {e}")

    # 2. Reset auction for next player
    auction.current_player_id = None
    auction.current_player_bid_start = None
    auction.current_bid_amount = 0
    db.commit()
