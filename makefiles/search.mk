# ---- Helpers -----------------------------------------------------------------
.PHONY: help-search
help-search:
	@echo "Targets:"
	@echo "  update   				 - update candidates base"
	@echo "  playlist  			  	 - create playlist.txt"
	@echo "  clean        		 - clear base and playlist"

# ---- Search ------------------------------------------------------------------

update:
	$(PYTHON) -m search.cli update-db --verbose

playlist:
	$(PYTHON) -m search.cli build-playlist

clean:
	rm -f search/db.sqlite search/playlist.txt
