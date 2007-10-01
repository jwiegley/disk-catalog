//
//  NSMetadataItem_XMLExtensions.h
//  mdfind2
//
//  Created by Jonathan Wight on 05/26/2005.
//  Copyright (c) 2005 Toxic Software. All rights reserved.
//

#import <Foundation/Foundation.h>

/**
 * @category NSMetadataItem (NSMetadataItem_XMLExtensions)
 */
@interface NSMetadataItem (NSMetadataItem_XMLExtensions)

- (NSXMLElement *)asXMLElement;
- (NSArray *)allAttributes;
- (NSString *)displayName;

@end
