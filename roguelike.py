#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import random
import struct
import sys
import re
import argparse
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog
import threading
import time
import io
from contextlib import redirect_stdout

class RogueLike:
    def __init__(self, config_file='roguelike.conf', debug_mode=False, gui_output=None):
        # Initialize characteristics lists and settings
        self.marshal_skills = []     # 元帥特性
        self.commander_skills = []   # 主將特性
        self.personal_skills = []    # 个人特性
        
        # Debug mode
        self.debug_mode = debug_mode
        
        # GUI output function for displaying progress
        self.gui_output = gui_output
        
        # Settings
        self.pick_limit = 5
        self.reroll_limit = 3  # Maximum consecutive failures before stopping
        self.extra_attribute = 30
        self.str_rate = 1.5
        self.int_rate = 1.0
        self.random_extra_attribute_min = -30
        self.random_extra_attribute_max = 30
        self.str_random_rate = 1.0
        self.int_random_rate = 1.0
        
        # Configurable threshold and rate values
        self.attribute_thresholds = [100, 130, 160, 190]
        self.attribute_rates = [1.4, 1.25, 1.1, 1.0, 0.9]
        
        # Rate for existing skills
        self.exist_attribute_rate = 0.7
        
        # Character processing limit
        self.last_character_number = 831
        
        # Load configuration
        self.load_config(config_file)
        
    # Add custom print function that can output to GUI if available
    def print(self, message):
        print(message)  # Always print to console
        if self.gui_output:
            self.gui_output(message)  # Also send to GUI if available
            
    # Add debug print function that only prints in debug mode
    def debug_print(self, message):
        if self.debug_mode:
            self.print(message)  # Only print debug messages when debug mode is enabled

    def load_config(self, config_file):
        """Load configuration from the specified file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for section headers
                if line == '元帥':
                    current_section = 'marshal'
                    continue
                elif line == '主將':
                    current_section = 'commander'
                    continue
                elif line == '个人':
                    current_section = 'personal'
                    continue
                
                # Parse settings
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'pick_limit':
                        self.pick_limit = int(value)
                    elif key == 'reroll_limit':
                        self.reroll_limit = int(value)
                    elif key == 'extra_attribute':
                        self.extra_attribute = int(value)
                    elif key == 'str_rate':
                        self.str_rate = float(value)
                    elif key == 'int_rate':
                        self.int_rate = float(value)
                    elif key == 'random_extra_attribute_min':
                        self.random_extra_attribute_min = int(value)
                    elif key == 'random_extra_attribute_max':
                        self.random_extra_attribute_max = int(value)
                    elif key == 'str_random_rate':
                        self.str_random_rate = float(value)
                    elif key == 'int_random_rate':
                        self.int_random_rate = float(value)
                    elif key == 'attribute_thresholds':
                        try:
                            self.attribute_thresholds = json.loads(value)
                        except json.JSONDecodeError:
                            print(f"Warning: Invalid attribute_thresholds format: {value}. Using default.")
                    elif key == 'attribute_rates':
                        try:
                            self.attribute_rates = json.loads(value)
                            if len(self.attribute_rates) != len(self.attribute_thresholds) + 1:
                                print(f"Warning: attribute_rates should have {len(self.attribute_thresholds) + 1} values. Using default.")
                                self.attribute_rates = [1.4, 1.25, 1.1, 1.0, 0.9]
                        except json.JSONDecodeError:
                            print(f"Warning: Invalid attribute_rates format: {value}. Using default.")
                    elif key == 'exist_attribute_rate':
                        self.exist_attribute_rate = float(value)
                    elif key == 'last_character_number':
                        self.last_character_number = int(value)
                    continue
                
                # Parse skill data
                if current_section and ';' in line:
                    parts = line.split(';')
                    if len(parts) >= 4:
                        skill_id = int(parts[0])
                        skill_name = parts[1]
                        skill_desc = parts[2]
                        skill_value = int(parts[3])
                        
                        skill_data = {
                            'id': skill_id,
                            'name': skill_name,
                            'desc': skill_desc,
                            'value': skill_value,
                            'bit': skill_id  # Use the skill ID directly as the bit position
                        }
                        
                        if current_section == 'marshal':
                            self.marshal_skills.append(skill_data)
                        elif current_section == 'commander':
                            self.commander_skills.append(skill_data)
                        elif current_section == 'personal':
                            self.personal_skills.append(skill_data)
        
        except Exception as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def process_save_file(self, input_file, output_file=None):
        """Process the save file and modify character attributes."""
        try:
            # Read the entire save file
            with open(input_file, 'rb') as f:
                save_data = bytearray(f.read())
            
            # Initialize counters for overall statistics
            total_skills_added = 0
            total_characters = 0  # total characters found
            characters_processed = 0  # characters with skills added
            
            # New search pattern for characters
            # Pattern: [char_id 2 bytes] [any 2 bytes] [Mark\0] [char_id 2 bytes] [any 2 bytes] [Mark\0\0\0\0\0]
            # Configurable starting search position - this can be 0x20000 or 0x34000 or any other address
            # The search will always scan the entire file until it finds Character #1
            search_position = 0x20000
            
            self.print(f"\n{'='*50}")
            self.print(f"SEARCHING FOR CHARACTERS BASED ON PATTERN")
            self.print(f"{'='*50}")
            self.print(f"Starting search from position 0x{search_position:X}")
            
            # Variables to track progress in non-debug mode
            processed_count = 0
            last_progress_update = 0
            
            # Process characters until we reach last_character_number
            for expected_char_id in range(1, self.last_character_number + 1):
                # For character ID, we only need the first 2 bytes (little-endian)
                char_id_bytes = struct.pack('<i', expected_char_id)[:2]
                
                # Initialize pattern search
                pattern_found = False
                pattern_pos = -1
                
                # Debug: for Character #1 only, search extensively and show what we find
                if expected_char_id == 1 and self.debug_mode:
                    self.debug_print(f"\nDEBUG - Searching extensively for Character #{expected_char_id}")
                    self.debug_print(f"Expected character ID bytes: {' '.join([f'{b:02X}' for b in char_id_bytes])}")
                    self.debug_print(f"Starting search from 0x{search_position:X}")
                    
                    # For Character #1, search the entire file if needed
                    # We don't want to risk missing Character #1 no matter where it is in the file
                    search_end = len(save_data) - 30  # Ensure we have enough bytes for the pattern
                    
                    # Look for the exact pattern for Character #1
                    for i in range(search_position, search_end):
                        if (save_data[i:i+2] == char_id_bytes and 
                            i+22 <= len(save_data) and  # Ensure we don't go past the end of the file
                            save_data[i+4:i+9] == b'\x4D\x61\x72\x6B\x00' and  # "Mark\0"
                            save_data[i+9:i+11] == char_id_bytes and
                            save_data[i+13:i+22] == b'\x4D\x61\x72\x6B\x00\x00\x00\x00\x00'):  # Complete pattern
                            self.debug_print(f"Found potential pattern at 0x{i:X}:")
                            self.debug_print(f"  {' '.join([f'{b:02X}' for b in save_data[i:i+30]])}")
                            
                            # Set this as the found pattern for Character #1
                            pattern_pos = i
                            pattern_found = True
                            break  # Found a complete match, so exit the loop
                
                # If we haven't found character #1 yet through the debug search, proceed with regular search
                if not pattern_found:
                    # For Character #1, we'll search the entire file if necessary
                    # For other characters, we'll use a more limited search range of 1200 bytes
                    if expected_char_id == 1:
                        # Use a very large search range for Character #1 - scan almost the entire file
                        max_search_position = len(save_data) - 25
                        self.print(f"Performing exhaustive search for Character #{expected_char_id} from 0x{search_position:X} to 0x{max_search_position:X}")
                    else:
                        # For subsequent characters, search within 1200 bytes from the current position
                        max_search_position = search_position + 1200
                        if max_search_position > len(save_data) - 25:
                            max_search_position = len(save_data) - 25
                    
                    # Search for the specified pattern exactly as described by the user:
                    # {char_id 2 bytes} {any 2 bytes} 4D 61 72 6B 00 {char_id 2 bytes} {any 2 bytes} 4D 61 72 6B 00 00 00 00 00
                    for i in range(search_position, max_search_position):
                        # Ensure we don't go past the end of the file with our checks
                        if i + 22 > len(save_data):
                            continue
                            
                        # 1. Check first 2 bytes match character ID
                        if save_data[i:i+2] != char_id_bytes:
                            continue
                            
                        # 2. Skip any 2 bytes (i+2:i+4)
                        
                        # 3. Check "Mark\0" at position i+4
                        if save_data[i+4:i+9] != b'\x4D\x61\x72\x6B\x00':
                            continue
                            
                        # 4. Check second occurrence of character ID at position i+9
                        if save_data[i+9:i+11] != char_id_bytes:
                            continue
                            
                        # 5. Skip any 2 bytes (i+11:i+13)
                        
                        # 6. Check "Mark\0\0\0\0\0" at position i+13
                        if save_data[i+13:i+22] != b'\x4D\x61\x72\x6B\x00\x00\x00\x00\x00':
                            continue
                            
                        # If we get here, we've found a match
                        pattern_pos = i
                        pattern_found = True
                        
                        # Always print the found character in both debug and non-debug mode
                        self.print(f"Found character #{expected_char_id} at 0x{i:X}")
                        if self.debug_mode:
                            self.debug_print(f"Pattern: {' '.join([f'{b:02X}' for b in save_data[i:i+22]])}")
                        
                        break
                
                if not pattern_found:
                    # Character #1 must be found; for others, we can continue with the next character ID
                    if expected_char_id == 1:
                        # Make one final attempt with an even more flexible pattern match
                        self.print(f"\nMaking final attempt to find Character #{expected_char_id}")
                        
                        # Scan almost the entire file for a more flexible pattern
                        search_end = len(save_data) - 25
                        for i in range(search_position, search_end):
                            # Use a more flexible pattern match for the final attempt
                            # Just look for the character ID followed by "Mark\0" in various positions
                            if i + 22 > len(save_data):
                                continue
                                
                            if save_data[i:i+2] == char_id_bytes:
                                # Check for Mark\0 in possible positions
                                if ((i+4 < len(save_data) and save_data[i+4:i+9] == b'\x4D\x61\x72\x6B\x00') or
                                    (i+13 < len(save_data) and save_data[i+13:i+18] == b'\x4D\x61\x72\x6B\x00')):
                                    
                                    # Also check for a second occurrence of the character ID
                                    second_id_pos = -1
                                    for j in range(i+2, min(i+20, len(save_data)-2)):
                                        if save_data[j:j+2] == char_id_bytes:
                                            second_id_pos = j
                                            break
                                    
                                    if second_id_pos != -1:
                                        self.print(f"Found Character #{expected_char_id} with relaxed pattern match at 0x{i:X}")
                                        if self.debug_mode:
                                            self.debug_print(f"Bytes: {' '.join([f'{b:02X}' for b in save_data[i:i+30]])}")
                                        pattern_pos = i
                                        pattern_found = True
                                        break
                        
                        # If Character #1 is still not found after exhaustive search, stop processing
                        if not pattern_found:
                            self.print(f"Character #{expected_char_id} pattern not found after extensive search.")
                            self.print(f"Please verify the save file format and check if Character #1 exists.")
                            return False
                    else:
                        # For characters other than #1, just skip to the next character ID
                        self.print(f"Character #{expected_char_id} pattern not found, skipping to next character ID.")
                        # Keep search_position the same for the next character ID
                        continue
                
                # Found a character
                char_offset = pattern_pos
                total_characters += 1  # Count every character found
                
                # Update search position for next character - minimum 900 bytes after current pattern
                search_position = pattern_pos + 900
                
                # The pattern is 22 bytes long (up to the end of Mark\0\0\0\0\0)
                pattern_end = char_offset + 22
                
                # Read the next 4 bytes to determine the offset to strength value
                skip_value = struct.unpack('<i', save_data[pattern_end:pattern_end+4])[0]
                
                # Calculate offset to strength value
                strength_offset = pattern_end + 4
                if skip_value > 0:
                    strength_offset += skip_value * 4
                
                # Calculate offset to intelligence value (4 bytes after strength)
                intelligence_offset = strength_offset + 4
                
                self.print(f"\n{'='*40}")
                self.print(f"Processing Character #{expected_char_id} found at offset 0x{char_offset:X}")
                self.print(f"Strength value at offset 0x{strength_offset:X}, Intelligence at 0x{intelligence_offset:X}")
                self.print(f"{'='*40}")
                
                # Extract character stats for this character
                try:
                    strength = struct.unpack('<i', save_data[strength_offset:strength_offset + 4])[0]
                    intelligence = struct.unpack('<i', save_data[intelligence_offset:intelligence_offset + 4])[0]
                except Exception as e:
                    self.print(f"\n!!! ERROR: Failed to read character stats !!!")
                    self.print(f"Character #{expected_char_id} at offset 0x{char_offset:X}")
                    self.print(f"Exception: {e}")
                    self.print(f"Debug information: Attempted to read 4 bytes each at offsets 0x{strength_offset:X} and 0x{intelligence_offset:X}")
                    self.print(f"Stopping operation for safety.")
                    return False
                
                # Check for abnormal strength or intelligence values
                if strength < 20 or strength > 300 or intelligence < 20 or intelligence > 300:
                    self.print(f"\n!!! ABNORMAL STATS DETECTED !!!")
                    self.print(f"Character #{expected_char_id} at offset 0x{char_offset:X}")
                    self.print(f"Strength: {strength} (outside normal range of 20-150)")
                    self.print(f"Intelligence: {intelligence} (outside normal range of 20-150)")
                    
                    if self.debug_mode:
                        self.debug_print(f"Raw bytes - Strength: {' '.join([f'0x{b:02X}' for b in save_data[strength_offset:strength_offset + 4]])}")
                        self.debug_print(f"Raw bytes - Intelligence: {' '.join([f'0x{b:02X}' for b in save_data[intelligence_offset:intelligence_offset + 4]])}")
                        
                        # Just display detailed debug info without stopping
                        self.debug_print("Abnormal values detected. Continuing in debug mode with detailed information.")
                        
                        # Dump a larger section of memory around the character data for detailed debugging
                        debug_range_start = max(0, char_offset - 16)
                        debug_range_end = min(len(save_data), char_offset + 128)
                        self.debug_print(f"\nMemory dump from 0x{debug_range_start:X} to 0x{debug_range_end:X}:")
                        
                        for i in range(debug_range_start, debug_range_end, 16):
                            # Get a chunk of up to 16 bytes
                            chunk = save_data[i:min(i+16, debug_range_end)]
                            # Format as hex
                            hex_values = ' '.join([f'{b:02X}' for b in chunk])
                            # Format as ASCII (replacing non-printable characters with dots)
                            ascii_values = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in chunk])
                            # Print the line with address, hex values, and ASCII representation
                            self.debug_print(f"0x{i:08X}: {hex_values.ljust(48)} {ascii_values}")
                    else:
                        self.print("Abnormal values detected, but continuing without debug mode.")
                        self.print("Use --debug flag to see more detailed information about abnormal values.")
                
                # Skip invalid characters (strength and intelligence both 0 could indicate unused character slots)
                if strength == 0 and intelligence == 0:
                    self.print(f"Character #{expected_char_id} appears to be empty or invalid (zero stats). Skipping.")
                    continue
                
                # Validate stats are within reasonable ranges
                if strength < 0 or strength > 1000 or intelligence < 0 or intelligence > 1000:
                    self.print(f"Warning: Stats out of reasonable range. Capping at maximum values.")
                    strength = min(max(0, strength), 1000)
                    intelligence = min(max(0, intelligence), 1000)
                
                self.print(f"Character stats - Strength: {strength}, Intelligence: {intelligence}")
                
                # In debug mode, search for potential skill data
                if self.debug_mode and expected_char_id == 1:  # Only for the first character to avoid spam
                    self.debug_print("\n--- SEARCHING FOR POTENTIAL SKILL DATA ---")
                    # Look for a wider range of potential skill data patterns
                    search_range = 512  # Search up to 512 bytes after strength
                    potential_skills = []
                    
                    # First, get a memory dump of this region for analysis
                    self.debug_print(f"\nMemory region from strength offset (0x{strength_offset:X}) onwards:")
                    for offset in range(0, search_range, 16):
                        check_offset = strength_offset + offset
                        if check_offset + 16 <= len(save_data):
                            data_chunk = save_data[check_offset:check_offset+16]
                            hex_values = ' '.join([f'{b:02X}' for b in data_chunk])
                            ascii_values = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in data_chunk])
                            self.debug_print(f"0x{check_offset:X} (+0x{offset:04X}): {hex_values.ljust(48)} {ascii_values}")
                    
                    # Now search for potential skill bit patterns
                    self.debug_print("\nPotential skill data locations:")
                    for offset in range(0, search_range, 4):
                        check_offset = strength_offset + offset
                        if check_offset + 32 <= len(save_data):  # Look for a 32-byte window
                            data_chunk = save_data[check_offset:check_offset+32]
                            
                            # Count bytes with some bits set but not all (typical for skill data)
                            sparse_bytes = sum(1 for b in data_chunk if 0 < b < 0xFF)
                            zero_bytes = sum(1 for b in data_chunk if b == 0)
                            
                            # Look for regions with a mix of zeros and sparse bytes
                            # Skill data typically has a few bytes with some bits set
                            if 2 <= sparse_bytes <= 8 and zero_bytes >= 16:
                                potential_skills.append(offset)
                                hex_values = ' '.join([f'{b:02X}' for b in data_chunk])
                                self.debug_print(f"Offset +0x{offset:04X} (0x{check_offset:X}): {hex_values}")
                                
                                # Check for common skill data patterns (frequently 0x01, 0x02, 0x04, etc.)
                                if any(b in [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80] for b in data_chunk):
                                    self.debug_print(f"  ^ High confidence - contains common skill bit patterns")
                    
                    # Analyze the results to guess the likely skill offsets
                    if potential_skills:
                        # Group potential skills by proximity (likely to be in groups)
                        skill_groups = []
                        current_group = [potential_skills[0]]
                        
                        for i in range(1, len(potential_skills)):
                            if potential_skills[i] - potential_skills[i-1] < 24:  # Close offsets
                                current_group.append(potential_skills[i])
                            else:
                                skill_groups.append(current_group)
                                current_group = [potential_skills[i]]
                        
                        if current_group:
                            skill_groups.append(current_group)
                        
                        self.debug_print("\nLikely skill offset groups:")
                        for i, group in enumerate(skill_groups):
                            self.debug_print(f"Group {i+1}: {', '.join([f'+0x{offset:X}' for offset in group])}")
                        
                        # Try to identify the three different skill types
                        if len(skill_groups) >= 3:
                            self.debug_print("\nPotential skill type offsets based on groups:")
                            skill_offsets = [group[0] for group in skill_groups[:3]]
                            skill_offsets.sort()  # Sort from smallest to largest
                            
                            # Assume smallest offset is personal, middle is commander, largest is marshal
                            # This is based on the original offsets (personal < commander < marshal)
                            personal_offset_guess = strength_offset + skill_offsets[0]
                            commander_offset_guess = strength_offset + skill_offsets[1]
                            marshal_offset_guess = strength_offset + skill_offsets[2]
                            
                            self.debug_print(f"Personal skills: +0x{skill_offsets[0]:X} (0x{personal_offset_guess:X})")
                            self.debug_print(f"Commander skills: +0x{skill_offsets[1]:X} (0x{commander_offset_guess:X})")
                            self.debug_print(f"Marshal skills: +0x{skill_offsets[2]:X} (0x{marshal_offset_guess:X})")
                    
                    self.debug_print("--- END OF SKILL DATA SEARCH ---\n")
                
                # Use offsets based on the confirmed structure
                # These are the confirmed offsets relative to the strength value
                personal_offset = strength_offset + 0x28C
                commander_offset = strength_offset + 0x29C
                marshal_offset = strength_offset + 0x2AC
                
                if self.debug_mode:
                    self.debug_print(f"DEBUG - Skill offsets (relative to strength value):")
                    self.debug_print(f"Marshal skills: +0x2AC (0x{marshal_offset:X})")
                    self.debug_print(f"Commander skills: +0x29C (0x{commander_offset:X})")
                    self.debug_print(f"Personal skills: +0x28C (0x{personal_offset:X})")
                
                # Calculate number of bytes needed for each skill type
                marshal_bytes_needed = (max([skill['id'] for skill in self.marshal_skills]) + 7) // 8
                commander_bytes_needed = (max([skill['id'] for skill in self.commander_skills]) + 7) // 8
                personal_bytes_needed = (max([skill['id'] for skill in self.personal_skills]) + 7) // 8
                
                # Extract skill bytes
                marshal_skill_bytes = bytearray(save_data[marshal_offset:marshal_offset + marshal_bytes_needed])
                commander_skill_bytes = bytearray(save_data[commander_offset:commander_offset + commander_bytes_needed])
                personal_skill_bytes = bytearray(save_data[personal_offset:personal_offset + personal_bytes_needed])
                
                # Determine which skills are already active
                active_marshal_skills = []
                active_commander_skills = []
                active_personal_skills = []
                
                # Lists to track newly added skills in this run
                added_marshal_skills = []
                added_commander_skills = []
                added_personal_skills = []
                
                self.debug_print("\n--- DEBUG: Reading skill bits from save file ---")
                self.debug_print(f"Marshal skills offset: 0x{marshal_offset:X}")
                self.debug_print(f"Commander skills offset: 0x{commander_offset:X}")
                self.debug_print(f"Personal skills offset: 0x{personal_offset:X}")
                self.debug_print(f"Marshal skill bytes: {' '.join([f'0x{b:02X}' for b in marshal_skill_bytes])}")
                self.debug_print(f"Commander skill bytes: {' '.join([f'0x{b:02X}' for b in commander_skill_bytes])}")
                self.debug_print(f"Personal skill bytes: {' '.join([f'0x{b:02X}' for b in personal_skill_bytes])}")
                self.debug_print("--- End of debug info ---\n")
                
                for skill in self.marshal_skills:
                    # Skip disabled skills (value = -1)
                    if skill['value'] == -1:
                        continue
                        
                    byte_index = skill['bit'] // 8
                    bit_position = skill['bit'] % 8
                    if byte_index < len(marshal_skill_bytes) and (marshal_skill_bytes[byte_index] & (1 << bit_position)):
                        active_marshal_skills.append(skill)
                        self.debug_print(f"DEBUG - Found active marshal skill: {skill['name']} (ID: {skill['id']}, Address: 0x{marshal_offset + byte_index:X}, Bit: {bit_position})")
                
                for skill in self.commander_skills:
                    # Skip disabled skills (value = -1)
                    if skill['value'] == -1:
                        continue
                        
                    byte_index = skill['bit'] // 8
                    bit_position = skill['bit'] % 8
                    if byte_index < len(commander_skill_bytes) and (commander_skill_bytes[byte_index] & (1 << bit_position)):
                        active_commander_skills.append(skill)
                        self.debug_print(f"DEBUG - Found active commander skill: {skill['name']} (ID: {skill['id']}, Address: 0x{commander_offset + byte_index:X}, Bit: {bit_position})")
                
                for skill in self.personal_skills:
                    # Skip disabled skills (value = -1)
                    if skill['value'] == -1:
                        continue
                        
                    byte_index = skill['bit'] // 8
                    bit_position = skill['bit'] % 8
                    if byte_index < len(personal_skill_bytes) and (personal_skill_bytes[byte_index] & (1 << bit_position)):
                        active_personal_skills.append(skill)
                        self.debug_print(f"DEBUG - Found active personal skill: {skill['name']} (ID: {skill['id']}, Address: 0x{personal_offset + byte_index:X}, Bit: {bit_position})")
                
                self.debug_print(f"Active skills - Marshal: {len(active_marshal_skills)}, Commander: {len(active_commander_skills)}, Personal: {len(active_personal_skills)}")
                
                # Calculate maximum attribute value
                max_attribute_value = 233 + self.extra_attribute
                
                # Calculate current attribute value from active skills - filter out any skills with value -1 (should be none at this point)
                # Apply exist_attribute_rate to existing skills
                active_skill_value = sum(skill['value'] * self.exist_attribute_rate for skill in active_marshal_skills + active_commander_skills + active_personal_skills if skill['value'] != -1)
                self.debug_print(f"Active skill value (with exist_attribute_rate {self.exist_attribute_rate}): {active_skill_value:.2f}")
                
                # Calculate the random extra attributes
                random_extra = random.randint(self.random_extra_attribute_min, self.random_extra_attribute_max)
                
                # Calculate current attribute value
                current_attribute_value = (strength * self.str_rate + 
                                          intelligence * self.int_rate + 
                                          random_extra + 
                                          active_skill_value)
                
                self.debug_print(f"Initial attribute values - Max: {max_attribute_value}, Current: {current_attribute_value:.2f}, Random Extra: {random_extra}")
                
                # Adjust max_attribute_value based on current value and configurable thresholds
                rate_index = len(self.attribute_thresholds)  # Default to the last rate (for values above all thresholds)
                for i, threshold in enumerate(self.attribute_thresholds):
                    if current_attribute_value < threshold:
                        rate_index = i
                        break
                        
                max_attribute_value = max_attribute_value * self.attribute_rates[rate_index]
                
                self.debug_print(f"Adjusted max attribute value: {max_attribute_value:.2f} (used rate: {self.attribute_rates[rate_index]})")
                
                # Calculate max random value
                max_random = strength * self.str_random_rate + intelligence * self.int_random_rate
                
                # Main loop to add new skills
                consecutive_failures = 0
                skill_type = 'personal'  # Initialize to avoid reference error
                
                while consecutive_failures < self.reroll_limit:
                    # Get a random value
                    random_value = random.randint(0, max(1, int(max_random) - 1))
                    
                    # Determine which type of skill to add
                    if random_value < strength * self.str_random_rate:
                        # Add personal skill
                        skill_type = 'personal'
                        skill_added, new_skill = self._try_add_skill('personal', personal_skill_bytes, active_personal_skills, current_attribute_value, max_attribute_value)
                        if skill_added and new_skill:
                            added_personal_skills.append(new_skill)
                    else:
                        # Add marshal or commander skill
                        skill_type = 'marshal' if random.randint(0, 2) == 0 else 'commander'
                        if skill_type == 'marshal':
                            skill_added, new_skill = self._try_add_skill('marshal', marshal_skill_bytes, active_marshal_skills, current_attribute_value, max_attribute_value)
                            if skill_added and new_skill:
                                added_marshal_skills.append(new_skill)
                        else:
                            skill_added, new_skill = self._try_add_skill('commander', commander_skill_bytes, active_commander_skills, current_attribute_value, max_attribute_value)
                            if skill_added and new_skill:
                                added_commander_skills.append(new_skill)
                    
                    if skill_added:
                        consecutive_failures = 0
                        # Update current_attribute_value with the new skill value
                        if skill_type == 'personal':
                            current_attribute_value += active_personal_skills[-1]['value']
                        elif skill_type == 'marshal':
                            current_attribute_value += active_marshal_skills[-1]['value']
                        else:  # commander
                            current_attribute_value += active_commander_skills[-1]['value']
                    else:
                        consecutive_failures += 1
                    
                    # Check if all skills are added
                    if (len(active_marshal_skills) == len(self.marshal_skills) and 
                        len(active_commander_skills) == len(self.commander_skills) and 
                        len(active_personal_skills) == len(self.personal_skills)):
                        self.debug_print("All skills are already added, stopping.")
                        break
                
                # Count total added skills for this character
                char_skills_added = len(added_marshal_skills) + len(added_commander_skills) + len(added_personal_skills)
                total_skills_added += char_skills_added
                
                if char_skills_added > 0:
                    characters_processed += 1
                
                # Print summary of added skills for this character
                self.debug_print(f"\n=== SUMMARY OF NEWLY ADDED SKILLS FOR CHARACTER #{expected_char_id} ===")
                self.debug_print(f"Total skills added: {char_skills_added}")
                
                if added_marshal_skills:
                    self.debug_print("\nAdded Marshal Skills (元帥特性):")
                    for skill in added_marshal_skills:
                        self.debug_print(f"  - {skill['name']} (ID: {skill['id']}, Value: {skill['value']})")
                
                if added_commander_skills:
                    self.debug_print("\nAdded Commander Skills (主將特性):")
                    for skill in added_commander_skills:
                        self.debug_print(f"  - {skill['name']} (ID: {skill['id']}, Value: {skill['value']})")
                
                if added_personal_skills:
                    self.debug_print("\nAdded Personal Skills (个人特性):")
                    for skill in added_personal_skills:
                        self.debug_print(f"  - {skill['name']} (ID: {skill['id']}, Value: {skill['value']})")
                
                self.debug_print("=====================================\n")
                
                # Update the save file with modified skill bytes for this character
                self.debug_print(f"--- DEBUG: Writing modified skill bytes back to save file for Character #{expected_char_id} ---")
                self.debug_print(f"Updating marshal skills at offset 0x{marshal_offset:X}: {' '.join([f'0x{b:02X}' for b in marshal_skill_bytes])}")
                for i, b in enumerate(marshal_skill_bytes):
                    save_data[marshal_offset + i] = b
                
                self.debug_print(f"Updating commander skills at offset 0x{commander_offset:X}: {' '.join([f'0x{b:02X}' for b in commander_skill_bytes])}")
                for i, b in enumerate(commander_skill_bytes):
                    save_data[commander_offset + i] = b
                
                self.debug_print(f"Updating personal skills at offset 0x{personal_offset:X}: {' '.join([f'0x{b:02X}' for b in personal_skill_bytes])}")
                for i, b in enumerate(personal_skill_bytes):
                    save_data[personal_offset + i] = b
                
                self.debug_print("--- End of debug info ---\n")
                
                self.debug_print(f"Character #{expected_char_id} final attribute value: {current_attribute_value:.2f}")
                
                # In non-debug mode, only show occasional progress updates
                if not self.debug_mode:
                    processed_count += 1
                    # Show progress every 10 characters or when we find character #1
                    if expected_char_id == 1 or processed_count - last_progress_update >= 10:
                        self.print(f"Processing character #{expected_char_id}...")
                        last_progress_update = processed_count
            
            # Generate output filename if not provided
            if output_file is None:
                output_file = os.path.splitext(input_file)[0] + "_roguelike.sav"
            
            # Write the modified save file
            with open(output_file, 'wb') as f:
                f.write(save_data)
            
            # Print overall summary
            self.debug_print(f"\n{'='*50}")
            self.debug_print(f"PROCESSING COMPLETE")
            self.debug_print(f"{'='*50}")
            self.debug_print(f"Total characters found: {total_characters} out of {self.last_character_number}")
            self.debug_print(f"Characters with skills modified: {characters_processed}")
            self.debug_print(f"Total skills added across all characters: {total_skills_added}")
            self.debug_print(f"Modified save file written to {output_file}")
            
            # Add a basic summary for non-debug mode
            if not self.debug_mode:
                self.print(f"\nProcessing complete. Added {total_skills_added} skills across {characters_processed} characters.")
                self.print(f"Modified save file written to {output_file}")
            
            # Return statistics instead of just True
            return (total_characters, characters_processed, total_skills_added)
            
        except Exception as e:
            self.print(f"Error processing save file: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _try_add_skill(self, skill_type, skill_bytes, active_skills, current_attribute, max_attribute):
        """Try to add a new skill of the specified type."""
        # No need to calculate absolute address now since we're working with direct offsets
        
        # Get list of skills not yet active
        all_skills = []
        if skill_type == 'marshal':
            all_skills = self.marshal_skills
        elif skill_type == 'commander':
            all_skills = self.commander_skills
        else:  # personal
            all_skills = self.personal_skills
        
        # Get list of skills not yet active
        available_skills = [skill for skill in all_skills if skill not in active_skills and skill['value'] != -1]
        
        if not available_skills:
            self.debug_print(f"No more {skill_type} skills available to add.")
            return False, None
        
        # Try to add a new skill, up to pick_limit attempts
        for _ in range(self.pick_limit):
            # Randomly select a skill
            skill = random.choice(available_skills)
            
            # Check if we can add this skill (attribute value constraint)
            if max_attribute - current_attribute < skill['value']:
                self.debug_print(f"Cannot add {skill_type} skill '{skill['name']}' (value {skill['value']}) - would exceed max attribute.")
                continue
            
            # Add the skill
            byte_index = skill['bit'] // 8
            bit_position = skill['bit'] % 8
            
            # Ensure skill_bytes is long enough
            while len(skill_bytes) <= byte_index:
                skill_bytes.append(0)
            
            # Set the bit
            skill_bytes[byte_index] |= (1 << bit_position)
            
            # Add to active skills
            active_skills.append(skill)
            
            self.debug_print(f"Added {skill_type} skill: {skill['name']} (value: {skill['value']})")
            self.debug_print(f"DEBUG - Setting bit at byte_index: {byte_index}, bit_position: {bit_position}")
            self.debug_print(f"DEBUG - Bit pattern: 0x{skill_bytes[byte_index]:02X} (after setting bit {bit_position})")
            
            return True, skill
        
        self.debug_print(f"Failed to add any {skill_type} skill after {self.pick_limit} attempts.")
        return False, None

class ProgressWindow:
    def __init__(self, title="RogueLike Save Processor"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("700x500")
        self.root.minsize(600, 400)
        
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # Create a frame for the text area
        frame = tk.Frame(self.root)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        
        # Create scrolled text widget
        self.text_area = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=80, height=24)
        self.text_area.grid(row=0, column=0, sticky="nsew")
        self.text_area.config(state=tk.DISABLED)  # Make it read-only
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, sticky="ew")
        
        # Cancel button
        self.cancel_button = tk.Button(self.root, text="Cancel", command=self.on_cancel)
        self.cancel_button.grid(row=2, column=0, pady=5)
        
        # Variable to track if cancel was pressed
        self.cancelled = False
        
        # Update the UI
        self.root.update()
    
    def append_text(self, text):
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, text + "\n")
        self.text_area.see(tk.END)  # Scroll to the end
        self.text_area.config(state=tk.DISABLED)
        self.root.update()
    
    def set_status(self, status):
        self.status_var.set(status)
        self.root.update()
    
    def on_cancel(self):
        if messagebox.askyesno("Cancel Operation", "Are you sure you want to cancel the operation?"):
            self.cancelled = True
            self.append_text("Cancellation requested. Waiting for current operation to complete...")
            self.set_status("Cancelling...")
    
    def close(self):
        self.root.destroy()

def process_with_gui(save_file, config_file='roguelike.conf', debug_mode=False, save_prefix=None):
    """Process a save file with GUI progress window"""
    progress_window = ProgressWindow()
    
    # Function to handle output to GUI
    def gui_output(message):
        progress_window.append_text(message)
    
    # Run processing in a separate thread
    def run_processing():
        try:
            progress_window.set_status("Initializing...")
            roguelike = RogueLike(config_file, debug_mode=debug_mode, gui_output=gui_output)
            
            # After processing, get save number from user first
            progress_window.set_status("请输入存档编号(1~98)")
            progress_window.append_text("\n请输入存档编号(1~98)。")
            
            # Get the save number before processing
            save_number = get_save_number_via_gui()
            if save_number is None:
                progress_window.append_text("存档编号选择已取消。使用默认文件名。")
                # Process with default output name
                progress_window.set_status("Processing save file...")
                result = roguelike.process_save_file(save_file)
            else:
                # Create the output filename with the save number
                if save_prefix:
                    new_output_file = f"{save_prefix}-{save_number:03d}.sav"
                    progress_window.append_text(f"将保存修改后的文件为: {new_output_file}")
                    
                    # Process and save directly to the numbered file
                    progress_window.set_status("Processing save file...")
                    result = roguelike.process_save_file(save_file, new_output_file)
                else:
                    # No prefix available, use default output
                    progress_window.append_text("无法确定前缀，将使用默认文件名。")
                    progress_window.set_status("Processing save file...")
                    result = roguelike.process_save_file(save_file)
            
            if isinstance(result, tuple) and len(result) == 3:
                total_characters, modified_characters, total_skills_added = result
                
                # Get the output file name
                output_file = os.path.splitext(save_file)[0] + "_roguelike.sav"
                if save_number is not None and save_prefix:
                    output_file = f"{save_prefix}-{save_number:03d}.sav"
                
                # Show completion message with statistics
                completion_msg = (
                    f"已操作 {total_characters} 武将，修改 {modified_characters} 武将，"
                    f"增加 {total_skills_added} 特性，档案储存为 {output_file}\n"
                    f"覆盖回游戏 save 资料夹读取对应编号存档即可"
                )
                
                progress_window.append_text("\n" + completion_msg)
                progress_window.set_status("处理完成")
                
                # Show message box and exit program after user clicks OK
                progress_window.root.after(100, lambda: show_completion_and_exit(completion_msg))
                
            elif result:
                progress_window.set_status("Processing completed successfully")
                progress_window.append_text("\nProcessing completed successfully. You may close this window.")
            else:
                progress_window.set_status("Processing failed")
                progress_window.append_text("\nProcessing failed. Please check the log for details.")
            
            # Enable close button
            progress_window.cancel_button.config(text="Close")
        except Exception as e:
            progress_window.append_text(f"\nError: {str(e)}")
            progress_window.set_status("Error occurred")
    
    # Function to show completion message and exit program
    def show_completion_and_exit(message):
        messagebox.showinfo("处理完成", message)
        progress_window.root.quit()  # Stop the mainloop
        progress_window.root.destroy()  # Destroy the window
        sys.exit(0)  # Exit the program with success code
    
    # Start processing thread
    processing_thread = threading.Thread(target=run_processing)
    processing_thread.daemon = True
    processing_thread.start()
    
    # Run the GUI main loop
    progress_window.root.mainloop()

def get_save_number_via_gui():
    """
    Display a dialog to get a save number from the user.
    Returns the number (1-98) or None if cancelled.
    """
    root = tk.Tk()
    root.withdraw()
    
    while True:
        # Show a custom dialog to get save number
        save_number_str = tk.simpledialog.askstring(
            "Save Number", 
            "请输入存档编号 (1-98):",
            parent=root
        )
        
        # User cancelled
        if save_number_str is None:
            root.destroy()
            return None
            
        # Validate input
        try:
            save_number = int(save_number_str)
            if 1 <= save_number <= 98:
                root.destroy()
                return save_number
            else:
                messagebox.showerror("Invalid Number", "存档编号必须在 1-98 之间。")
        except ValueError:
            messagebox.showerror("Invalid Input", "请输入有效的数字。")
    
    # This should never be reached
    root.destroy()
    return None

def main():
    parser = argparse.ArgumentParser(description='RogueLike Save File Processor')
    parser.add_argument('save_file', nargs='?', help='Path to the save file to process')
    parser.add_argument('--config', default='roguelike.conf', help='Path to the configuration file')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with additional checks and detailed error messages')
    parser.add_argument('--no-gui', action='store_true', help='Disable GUI even when no save file is provided')
    
    args = parser.parse_args()
    
    # Determine if we should use GUI mode
    use_gui = not args.no_gui and not args.save_file
    
    # If no save file is provided via command line, show a GUI file picker
    save_file = args.save_file
    save_prefix = None
    
    if not save_file:
        result = select_file_via_gui()
        if not result:  # User cancelled the file selection
            print("No save file selected. Exiting...")
            return 1
        
        save_file, save_prefix = result
        use_gui = True  # If file was selected via GUI, continue in GUI mode
    else:
        # For command-line provided files, try to extract prefix
        file_name = os.path.basename(save_file)
        match = re.match(r'^(.+)-(\d{3})\.sav$', file_name)
        if match:
            save_prefix = match.group(1)
    
    # Check if the save file exists
    if not os.path.isfile(save_file):
        error_msg = f"Save file not found: {save_file}"
        if use_gui:
            messagebox.showerror("Error", error_msg)
        print(error_msg)
        return 1
    
    # Check if the config file exists
    if not os.path.isfile(args.config):
        error_msg = f"Configuration file not found: {args.config}"
        if use_gui:
            messagebox.showerror("Error", error_msg)
        print(error_msg)
        return 1
    
    if args.debug:
        print("DEBUG MODE ENABLED - Additional checks and detailed error messages will be shown")
    
    # Process the save file
    if use_gui:
        # Process in GUI mode
        process_with_gui(save_file, args.config, args.debug, save_prefix)
        return 0
    else:
        # Process in command-line mode
        roguelike = RogueLike(args.config, debug_mode=args.debug)
        result = roguelike.process_save_file(save_file)
        
        if result and isinstance(result, tuple) and len(result) == 3:
            total_characters, modified_characters, total_skills_added = result
            
            # For command line mode, we'll just use the original output file name logic
            output_file = os.path.splitext(save_file)[0] + "_roguelike.sav"
            
            print(f"Processing completed successfully.")
            print(f"Processed {total_characters} characters, modified {modified_characters}, added {total_skills_added} skills.")
            print(f"Modified save file written to {output_file}")
            return 0
        elif result:
            print("Processing completed successfully.")
            return 0
        else:
            print("Processing failed.")
            return 1

def select_file_via_gui():
    """
    Display a GUI file picker dialog to select a save file.
    Returns the selected file path, or None if the selection was cancelled.
    """
    # Hide the main Tkinter window
    root = tk.Tk()
    root.withdraw()
    
    # Create a simple info message
    messagebox.showinfo("三國群英傳7 RogueLike 存檔修改器", 
                        "请选择要修改的 .sav 存档(支援 1440 原版 & 修正版)\n製作者：軟絲, 特別感謝：天亮就分手")
    
    while True:
        # Show the file selection dialog
        file_path = filedialog.askopenfilename(
            title="Select Save File",
            filetypes=[("Save Files", "*.sav"), ("All Files", "*.*")]
        )
        
        # User cancelled the selection
        if not file_path:
            root.destroy()
            return None
            
        # Validate file name pattern
        file_name = os.path.basename(file_path)
        # Expected pattern: {prefix}-{000~098}.sav
        match = re.match(r'^(.+)-(\d{3})\.sav$', file_name)
        
        if match:
            # Extract prefix and number
            prefix = match.group(1)
            number = int(match.group(2))
            
            # Check if number is within valid range (000-098)
            if 0 <= number <= 98:
                # Valid file name
                root.destroy()
                return file_path, prefix
        
        # Invalid file name
        messagebox.showerror("Invalid File", "请选择有效且档名未修改的 sg7 存档\n\n预期格式: {prefix}-{000~098}.sav")
    
    # This should never be reached, but just in case
    root.destroy()
    return None

if __name__ == "__main__":
    sys.exit(main()) 