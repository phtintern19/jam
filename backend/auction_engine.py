import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# Throttle request-scoped ticks (Passenger-safe alternative to always-on threads)
_last_tick_at = 0.0
_tick_lock = threading.Lock()
_TICK_INTERVAL_SEC = float(os.getenv("AUCTION_TICK_INTERVAL", "5"))
_engine_thread_started = False


def manage_auctions_sync():
    """
    Core logic to transition events and auctions (sync — WSGI / Passenger safe).
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

            auction = db.query(models.Auction).filter(models.Auction.event_id == event.event_id).first()
            if not auction:
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

        for auction in active_auctions:
            event = auction.event
            if not event:
                continue

            if auction.current_player_id is None:
                auctioned_player_ids_q = db.query(models.Bid.player_id).filter(
                    models.Bid.auction_id == auction.auction_id
                ).distinct()
                auctioned_player_ids = [r[0] for r in auctioned_player_ids_q.all()]

                next_player = db.query(models.Player).join(models.Player.events).filter(
                    models.Event.event_id == event.event_id,
                    ~models.Player.player_id.in_(auctioned_player_ids)
                ).first()

                if next_player:
                    logger.info(
                        f"Starting bidding for player: {next_player.full_name} "
                        f"(ID: {next_player.player_id}) in auction {auction.auction_id}"
                    )
                    auction.current_player_id = next_player.player_id
                    auction.current_player_bid_start = now
                    auction.current_bid_amount = (
                        event.base_prices.get('Standard', 0) if event.base_prices else 0
                    )
                    db.commit()
                else:
                    logger.info(f"Auction {auction.auction_id} concluded. No more players.")
                    auction.status = 'completed'
                    event.status = 'completed'
                    event.is_live = False
                    db.commit()
            else:
                bid_time_limit = event.bid_time_limit or 20
                time_passed = (
                    (now - auction.current_player_bid_start).total_seconds()
                    if auction.current_player_bid_start else 0
                )

                if auction.current_player_bid_start and time_passed >= bid_time_limit:
                    process_bid_conclusion(db, auction)

    finally:
        db.close()


async def manage_auctions():
    """Async wrapper used by the optional background loop."""
    manage_auctions_sync()


async def auction_engine_loop():
    """Background loop that runs periodically to manage auction states."""
    logger.info("Starting background auction engine loop...")
    while True:
        try:
            await manage_auctions()
        except Exception as e:
            logger.error(f"Error in auction engine loop: {e}", exc_info=True)
        await asyncio.sleep(_TICK_INTERVAL_SEC)


def tick_auctions_if_due():
    """
    Run auction management at most once per AUCTION_TICK_INTERVAL seconds.
    Safe to call from Flask before_request under Passenger.
    """
    global _last_tick_at
    now = time.time()
    if (now - _last_tick_at) < _TICK_INTERVAL_SEC:
        return
    if not _tick_lock.acquire(blocking=False):
        return
    try:
        if (time.time() - _last_tick_at) < _TICK_INTERVAL_SEC:
            return
        manage_auctions_sync()
        _last_tick_at = time.time()
    except Exception as e:
        logger.error(f"Error in request-scoped auction tick: {e}", exc_info=True)
    finally:
        _tick_lock.release()


def start_auction_engine():
    """
    Start the auction engine in a background daemon thread.
    Prefer request-scoped ticks on cPanel; enable thread via env when workers stay alive.
    """
    global _engine_thread_started
    if _engine_thread_started:
        return
    _engine_thread_started = True

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auction_engine_loop())

    thread = threading.Thread(target=run_loop, daemon=True, name="auction-engine")
    thread.start()
    logger.info("Auction engine background thread started.")


def ensure_auction_engine():
    """
    Passenger bootstrap: always rely on lazy ticks; optionally start a thread.
    ENABLE_AUCTION_ENGINE_THREAD defaults to false on production-friendly setups.
    """
    use_thread = os.getenv("ENABLE_AUCTION_ENGINE_THREAD", "false").lower() == "true"
    if use_thread:
        start_auction_engine()
    # Immediate first tick so cold Passenger workers catch up
    tick_auctions_if_due()


def get_or_create_system_resources(db):
    """Ensure a system user, team owner, and team exist for 'unsold' bids."""
    system_user = db.query(models.User).filter(models.User.email == "system@bidzone.com").first()
    if not system_user:
        system_user = models.User(
            username="system_auction",
            email="system@bidzone.com",
            password_hash="system_password_hash_not_usable",
            user_type=models.UserType.admin,
            is_active=False
        )
        db.add(system_user)
        db.flush()

    system_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == system_user.user_id).first()
    if not system_owner:
        system_owner = models.TeamOwner(
            user_id=system_user.user_id,
            owner_name="System Auctioneer"
        )
        db.add(system_owner)
        db.flush()

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
    """Handle the end of a bidding phase for a player."""
    logger.info(
        f"Concluding bidding for player ID {auction.current_player_id} "
        f"in auction {auction.auction_id}"
    )

    highest_bid = db.query(models.Bid).filter(
        models.Bid.auction_id == auction.auction_id,
        models.Bid.player_id == auction.current_player_id
    ).order_by(models.Bid.amount.desc()).first()

    if highest_bid:
        highest_bid.status = 'won'
        logger.info(
            f"Player {auction.current_player_id} won by team {highest_bid.team_id} "
            f"for {highest_bid.amount}"
        )
        team = highest_bid.team
        if team and team.owner:
            team.owner.wallet_balance -= highest_bid.amount
    else:
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

    auction.current_player_id = None
    auction.current_player_bid_start = None
    auction.current_bid_amount = 0
    db.commit()
